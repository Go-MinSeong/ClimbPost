import SwiftUI
import AuthenticationServices

struct LoginView: View {
    @EnvironmentObject var authState: AuthState
    @StateObject private var authService = AuthService()
    @State private var appeared = false
    @State private var iconScale: CGFloat = 0.9
    @State private var showError = false

    var body: some View {
        ZStack {
            // Gradient background
            LinearGradient(
                colors: [
                    AppColor.background,
                    Color(red: 0.12, green: 0.12, blue: 0.22)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()

            VStack(spacing: 0) {
                Spacer()

                // Branding section
                VStack(spacing: 16) {
                    // Climbing icon with pulse animation
                    Image(systemName: "mountain.2.fill")
                        .font(.system(size: 80))
                        .foregroundStyle(
                            LinearGradient(
                                colors: [AppColor.accent, AppColor.accentDark],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .scaleEffect(iconScale)
                        .onAppear {
                            withAnimation(
                                .easeInOut(duration: 2.0)
                                .repeatForever(autoreverses: true)
                            ) {
                                iconScale = 1.05
                            }
                        }

                    Text("클라임포스트")
                        .font(AppFont.heroTitle)
                        .foregroundColor(.white)

                    Text("나의 클라이밍, 자동으로 분석하고 공유하세요")
                        .font(AppFont.caption)
                        .foregroundColor(.white.opacity(0.6))
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 32)
                }

                Spacer()

                // Sign in buttons
                VStack(spacing: 14) {
                    // Apple Sign In
                    SignInWithAppleButton(.signIn) { request in
                        request.requestedScopes = [.email, .fullName]
                    } onCompletion: { result in
                        Task {
                            await authService.handleAppleSignIn(result: result)
                        }
                    }
                    .signInWithAppleButtonStyle(.white)
                    .frame(height: 52)
                    .clipShape(Capsule())

                    // Google Sign In
                    Button {
                        Task { await authService.signInWithGoogle() }
                    } label: {
                        HStack(spacing: 8) {
                            Image(systemName: "g.circle.fill")
                                .font(.title2)
                            Text("Google로 로그인")
                                .font(.system(size: 16, weight: .medium, design: .rounded))
                        }
                        .frame(maxWidth: .infinity, minHeight: 52)
                        .background(Color.white)
                        .foregroundColor(.black)
                        .clipShape(Capsule())
                        .overlay(
                            Capsule()
                                .stroke(Color.white.opacity(0.2), lineWidth: 1)
                        )
                    }
                }
                .padding(.horizontal, 32)
                .disabled(authService.isAuthenticating)

                if authService.isAuthenticating {
                    ProgressView()
                        .tint(AppColor.accent)
                        .padding(.top, 16)
                }

                Spacer()
                    .frame(height: 60)
            }
            .opacity(appeared ? 1 : 0)
            .offset(y: appeared ? 0 : 20)

            // Error toast overlay
            if showError, let error = authService.errorMessage {
                VStack {
                    Spacer()
                    Text(error)
                        .font(AppFont.caption)
                        .foregroundColor(.white)
                        .padding(.horizontal, 20)
                        .padding(.vertical, 12)
                        .background(AppColor.fail.opacity(0.9))
                        .clipShape(Capsule())
                        .padding(.bottom, 100)
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                }
                .ignoresSafeArea()
            }
        }
        .onAppear {
            authService.configure(authState: authState)
            withAnimation(.easeOut(duration: 0.8)) {
                appeared = true
            }
        }
        .onChange(of: authService.errorMessage) { _, newValue in
            if newValue != nil {
                withAnimation { showError = true }
                DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                    withAnimation { showError = false }
                }
            }
        }
    }
}
