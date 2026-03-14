import Foundation

@MainActor
final class AuthState: ObservableObject {
    @Published var isLoggedIn = false
    @Published var isLoading = true
    @Published var currentUser: UserProfile?
    @Published var errorMessage: String?

    private let apiClient: APIClientProtocol

    init(apiClient: APIClientProtocol = APIClient.shared) {
        self.apiClient = apiClient
    }

    /// Check for existing token on app launch and validate it
    func checkExistingSession() async {
        guard KeychainHelper.load(.accessToken) != nil else {
            isLoading = false
            return
        }

        do {
            let user = try await apiClient.getMe()
            currentUser = user
            isLoggedIn = true
        } catch {
            // Token expired or invalid — try refresh
            do {
                let response = try await apiClient.refreshToken()
                KeychainHelper.save(response.accessToken, for: .accessToken)
                let user = try await apiClient.getMe()
                currentUser = user
                isLoggedIn = true
            } catch {
                // Refresh also failed — clear and require re-login
                KeychainHelper.clearAll()
                isLoggedIn = false
            }
        }

        isLoading = false
    }

    /// Handle login response from auth service
    func handleLoginSuccess(_ response: AuthResponse) {
        KeychainHelper.save(response.accessToken, for: .accessToken)
        KeychainHelper.save(response.userId, for: .userId)
        currentUser = UserProfile(userId: response.userId, email: nil, provider: "")
        isLoggedIn = true
        errorMessage = nil
    }

    func signOut() async {
        KeychainHelper.clearAll()
        currentUser = nil
        isLoggedIn = false
    }
}
