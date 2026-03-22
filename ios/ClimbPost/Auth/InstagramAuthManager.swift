import AuthenticationServices
import SwiftUI
import os.log

private let logger = Logger(subsystem: "com.climbpost", category: "InstagramAuth")

@MainActor
final class InstagramAuthManager: NSObject, ObservableObject {
    static let shared = InstagramAuthManager()

    @Published var isConnected = false
    @Published var igUsername: String?
    @Published var igProfilePicture: String?
    @Published var isAuthenticating = false
    @Published var errorMessage: String?

    private var authSession: ASWebAuthenticationSession?

    override init() {
        super.init()
    }

    // MARK: - Check Status

    func checkStatus() async {
        do {
            let status: InstagramAccountStatus = try await APIClient.shared.getInstagramStatus()
            isConnected = status.connected
            igUsername = status.igUsername
            igProfilePicture = status.igProfilePicture
        } catch {
            logger.error("Failed to check Instagram status: \(error.localizedDescription)")
        }
    }

    // MARK: - Start OAuth Flow

    func startLogin() {
        isAuthenticating = true
        errorMessage = nil

        Task {
            do {
                // Step 1: Get OAuth config from server
                let config: InstagramConnectInfo = try await APIClient.shared.getInstagramConnectInfo()

                // Step 2: Build Facebook OAuth URL
                let state = UUID().uuidString
                UserDefaults.standard.set(state, forKey: "fb_oauth_state")

                var components = URLComponents(string: "https://www.facebook.com/v21.0/dialog/oauth")!
                components.queryItems = [
                    URLQueryItem(name: "client_id", value: config.fbAppId),
                    URLQueryItem(name: "redirect_uri", value: config.redirectUri),
                    URLQueryItem(name: "scope", value: config.scopes),
                    URLQueryItem(name: "response_type", value: "code"),
                    URLQueryItem(name: "state", value: state),
                ]

                guard let authURL = components.url else {
                    errorMessage = "잘못된 OAuth URL"
                    isAuthenticating = false
                    return
                }

                // Step 3: Open ASWebAuthenticationSession
                let callbackScheme = config.redirectUri.components(separatedBy: "://").first ?? "climbpost"

                let session = ASWebAuthenticationSession(
                    url: authURL,
                    callbackURLScheme: callbackScheme
                ) { [weak self] callbackURL, error in
                    Task { @MainActor in
                        await self?.handleCallback(callbackURL: callbackURL, error: error)
                    }
                }

                session.presentationContextProvider = self
                session.prefersEphemeralWebBrowserSession = false
                session.start()
                authSession = session

            } catch {
                errorMessage = error.localizedDescription
                isAuthenticating = false
            }
        }
    }

    // MARK: - Handle Callback

    private func handleCallback(callbackURL: URL?, error: Error?) async {
        defer { isAuthenticating = false }

        if let error = error {
            if (error as? ASWebAuthenticationSessionError)?.code == .canceledLogin {
                return // User cancelled
            }
            errorMessage = error.localizedDescription
            return
        }

        guard let callbackURL = callbackURL,
              let components = URLComponents(url: callbackURL, resolvingAgainstBaseURL: false),
              let queryItems = components.queryItems else {
            errorMessage = "잘못된 콜백 URL"
            return
        }

        let params = Dictionary(uniqueKeysWithValues: queryItems.compactMap {
            guard let value = $0.value else { return nil as (String, String)? }
            return ($0.name, value)
        }.compactMap { $0 })

        // Verify CSRF state
        let savedState = UserDefaults.standard.string(forKey: "fb_oauth_state")
        guard params["state"] == savedState else {
            errorMessage = "보안 검증 실패 (CSRF)"
            return
        }

        guard let code = params["code"] else {
            errorMessage = params["error_description"] ?? params["error"] ?? "인증 실패"
            return
        }

        // Step 4: Send code to backend
        do {
            let result: InstagramAccountStatus = try await APIClient.shared.exchangeInstagramCode(code: code)
            isConnected = result.connected
            igUsername = result.igUsername
            igProfilePicture = result.igProfilePicture
            logger.info("Instagram connected: @\(result.igUsername ?? "unknown")")
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Disconnect

    func disconnect() async {
        do {
            try await APIClient.shared.disconnectInstagram()
            isConnected = false
            igUsername = nil
            igProfilePicture = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

// MARK: - ASWebAuthenticationPresentationContextProviding

extension InstagramAuthManager: ASWebAuthenticationPresentationContextProviding {
    nonisolated func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        return MainActor.assumeIsolated {
            UIApplication.shared.connectedScenes
                .compactMap { $0 as? UIWindowScene }
                .flatMap { $0.windows }
                .first { $0.isKeyWindow } ?? ASPresentationAnchor()
        }
    }
}
