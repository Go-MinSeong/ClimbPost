import SwiftUI
import AuthenticationServices

struct LoginView: View {
    @EnvironmentObject var authState: AuthState
    @StateObject private var authService = AuthService()

    var body: some View {
        VStack(spacing: 32) {
            Spacer()

            // App branding
            VStack(spacing: 12) {
                Image(systemName: "mountain.2.fill")
                    .font(.system(size: 72))
                    .foregroundStyle(.blue)

                Text("ClimbPost")
                    .font(.largeTitle.bold())

                Text("Analyze your climbing.\nShare your progress.")
                    .font(.body)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            Spacer()

            // Sign in buttons
            VStack(spacing: 16) {
                // Apple Sign In
                SignInWithAppleButton(.signIn) { request in
                    request.requestedScopes = [.email, .fullName]
                } onCompletion: { result in
                    Task {
                        await authService.handleAppleSignIn(result: result)
                    }
                }
                .signInWithAppleButtonStyle(.black)
                .frame(height: 50)
                .cornerRadius(10)

                // Google Sign In
                Button {
                    Task { await authService.signInWithGoogle() }
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: "g.circle.fill")
                            .font(.title2)
                        Text("Sign in with Google")
                            .font(.body.weight(.medium))
                    }
                    .frame(maxWidth: .infinity, minHeight: 50)
                    .background(Color(.systemBackground))
                    .foregroundStyle(.primary)
                    .cornerRadius(10)
                    .overlay(
                        RoundedRectangle(cornerRadius: 10)
                            .stroke(Color(.separator), lineWidth: 1)
                    )
                }
            }
            .padding(.horizontal, 24)
            .disabled(authService.isAuthenticating)

            if authService.isAuthenticating {
                ProgressView()
            }

            if let error = authService.errorMessage {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)
            }

            Spacer()
                .frame(height: 40)
        }
        .onAppear {
            authService.configure(authState: authState)
        }
    }
}
