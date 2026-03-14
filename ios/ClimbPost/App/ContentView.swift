import SwiftUI

struct ContentView: View {
    @EnvironmentObject var authState: AuthState

    var body: some View {
        Group {
            if authState.isLoading {
                ZStack {
                    AppColor.background.ignoresSafeArea()
                    VStack(spacing: 16) {
                        Image(systemName: "mountain.2.fill")
                            .font(.system(size: 48))
                            .foregroundStyle(AppColor.accent)
                        ProgressView()
                            .tint(AppColor.accent)
                    }
                }
            } else if authState.isLoggedIn {
                MainView()
                    .transition(.opacity)
            } else {
                LoginView()
                    .transition(.opacity)
            }
        }
        .animation(.easeInOut(duration: 0.4), value: authState.isLoggedIn)
        .animation(.easeInOut(duration: 0.4), value: authState.isLoading)
        .task {
            await authState.checkExistingSession()
        }
    }
}

struct MainView: View {
    @EnvironmentObject var authState: AuthState
    @EnvironmentObject var pushManager: PushManager
    @State private var showGallery = false
    @State private var pushSessionId: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    // Welcome card
                    welcomeCard

                    // Primary CTA
                    ctaButton

                    // Quick stats row
                    statsRow

                    // Recent sessions section
                    recentSessionsSection
                }
                .padding(.horizontal, 20)
                .padding(.top, 12)
                .padding(.bottom, 32)
            }
            .background(AppColor.background.ignoresSafeArea())
            .navigationTitle("홈")
            .navigationBarTitleDisplayMode(.large)
            .toolbarBackground(AppColor.background, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("로그아웃") {
                        Task { await authState.signOut() }
                    }
                    .font(AppFont.caption)
                    .foregroundColor(AppColor.accent)
                }
            }
            .navigationDestination(isPresented: $showGallery) {
                GalleryView()
            }
            .navigationDestination(item: $pushSessionId) { sessionId in
                ResultView(sessionId: sessionId)
            }
        }
        .onReceive(pushManager.$pendingSessionId) { sessionId in
            guard let sessionId else { return }
            pushSessionId = sessionId
            pushManager.pendingSessionId = nil
        }
    }

    // MARK: - Welcome Card

    private var welcomeCard: some View {
        HStack(spacing: 14) {
            // Avatar circle
            Circle()
                .fill(AppColor.accent.opacity(0.2))
                .frame(width: 50, height: 50)
                .overlay(
                    Image(systemName: "person.fill")
                        .foregroundColor(AppColor.accent)
                        .font(.title3)
                )

            VStack(alignment: .leading, spacing: 4) {
                Text("안녕하세요!")
                    .font(AppFont.sectionTitle)
                    .foregroundColor(.white)

                if let user = authState.currentUser {
                    Text(user.email ?? user.userId)
                        .font(AppFont.caption)
                        .foregroundColor(.white.opacity(0.6))
                }
            }

            Spacer()

            Image(systemName: "mountain.2.fill")
                .font(.title2)
                .foregroundStyle(AppColor.accent.opacity(0.4))
        }
        .padding(18)
        .background(AppColor.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    // MARK: - CTA Button

    private var ctaButton: some View {
        Button {
            showGallery = true
        } label: {
            HStack(spacing: 10) {
                Image(systemName: "video.badge.plus")
                    .font(.title3)
                Text("오늘의 영상 스캔")
            }
        }
        .buttonStyle(PrimaryButtonStyle())
    }

    // MARK: - Stats Row

    private var statsRow: some View {
        HStack(spacing: 12) {
            statCard(title: "총 세션", value: "—", icon: "calendar")
            statCard(title: "총 클립", value: "—", icon: "film.stack")
            statCard(title: "완등률", value: "—", icon: "trophy")
        }
    }

    private func statCard(title: String, value: String, icon: String) -> some View {
        VStack(spacing: 8) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundColor(AppColor.accent)

            Text(value)
                .font(AppFont.sectionTitle)
                .foregroundColor(.white)

            Text(title)
                .font(AppFont.caption)
                .foregroundColor(.white.opacity(0.5))
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 16)
        .background(AppColor.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    // MARK: - Recent Sessions

    private var recentSessionsSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("최근 세션")
                .font(AppFont.sectionTitle)
                .foregroundColor(.white)

            // Placeholder card
            VStack(spacing: 12) {
                Image(systemName: "tray")
                    .font(.largeTitle)
                    .foregroundColor(.white.opacity(0.2))

                Text("아직 분석된 세션이 없습니다")
                    .font(AppFont.cardTitle)
                    .foregroundColor(.white.opacity(0.4))

                Text("영상을 스캔하고 첫 세션을 시작하세요!")
                    .font(AppFont.caption)
                    .foregroundColor(.white.opacity(0.3))
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 32)
            .background(AppColor.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 16))
        }
    }
}
