import Foundation
import AuthenticationServices

@MainActor
final class AuthService: NSObject, ObservableObject {
    @Published var isAuthenticating = false
    @Published var errorMessage: String?

    private let apiClient: APIClientProtocol
    private var authState: AuthState?

    init(apiClient: APIClientProtocol = APIClient.shared) {
        self.apiClient = apiClient
    }

    func configure(authState: AuthState) {
        self.authState = authState
    }

    // MARK: - Apple Sign In

    func handleAppleSignIn(result: Result<ASAuthorization, Error>) async {
        isAuthenticating = true
        defer { isAuthenticating = false }

        switch result {
        case .success(let authorization):
            guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential,
                  let identityTokenData = credential.identityToken,
                  let idToken = String(data: identityTokenData, encoding: .utf8) else {
                errorMessage = "Failed to get Apple ID token"
                return
            }

            await loginWithServer(provider: "apple", idToken: idToken)

        case .failure(let error):
            if (error as NSError).code == ASAuthorizationError.canceled.rawValue {
                return // User cancelled, not an error
            }
            errorMessage = "Apple Sign In failed: \(error.localizedDescription)"
        }
    }

    // MARK: - Google Sign In

    func signInWithGoogle() async {
        isAuthenticating = true
        defer { isAuthenticating = false }

        // Google Sign-In requires GoogleSignIn SDK integration.
        // For now, this is a placeholder that will be connected
        // once the GoogleSignIn-iOS SPM package is added.
        errorMessage = "Google Sign In requires SDK integration — coming soon"
    }

    // MARK: - Server Login

    private func loginWithServer(provider: String, idToken: String) async {
        do {
            let response = try await apiClient.login(provider: provider, idToken: idToken)
            authState?.handleLoginSuccess(response)
        } catch {
            errorMessage = "Login failed: \(error.localizedDescription)"
        }
    }
}
