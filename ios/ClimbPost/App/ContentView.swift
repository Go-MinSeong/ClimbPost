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
                DemoFlowView()
                    .transition(.opacity)
            } else {
                LoginView()
                    .transition(.opacity)
            }
        }
        .animation(.easeInOut(duration: 0.4), value: authState.isLoggedIn)
        .animation(.easeInOut(duration: 0.4), value: authState.isLoading)
        .task {
            #if targetEnvironment(simulator)
            // Auto-login for simulator demo
            authState.handleLoginSuccess(AuthResponse(
                accessToken: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkZXYtdXNlci0wMDEiLCJleHAiOjE3NzQwOTA1NjgsImlhdCI6MTc3MzQ4NTc2OH0.LcNp93dekmQM3N4S0JfTFgk52egdRjo5vyqMIrz86ik",
                tokenType: "bearer",
                userId: "dev-user-001"
            ))
            authState.isLoading = false
            #else
            await authState.checkExistingSession()
            #endif
        }
    }
}

struct SessionSummary: Identifiable {
    let id: String  // gymId + date
    let gymName: String
    let date: String
    let clipCount: Int
    let successCount: Int
    let failCount: Int
}

struct MainView: View {
    @EnvironmentObject var authState: AuthState
    @EnvironmentObject var pushManager: PushManager
    @State private var showGallery = false
    @State private var pushSessionId: String?
    @State private var selectedSessionClips: [Clip]?

    // Home stats
    @State private var totalSessions: Int = 0
    @State private var totalClips: Int = 0
    @State private var successRate: String = "—"
    @State private var recentSessions: [SessionSummary] = []
    @State private var clipsBySession: [String: [Clip]] = [:]
    @State private var isLoadingHome = false

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
        .task {
            await loadHomeData()
        }
    }

    private func loadHomeData() async {
        guard !isLoadingHome else { return }
        isLoadingHome = true
        defer { isLoadingHome = false }

        do {
            let allClips = try await APIClient.shared.getAllClips()
            totalClips = allClips.count

            // Group clips by gymId + date (YYYY-MM-DD from createdAt) to derive sessions
            var grouped: [String: [Clip]] = [:]
            let dateFormatter = DateFormatter()
            dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
            dateFormatter.locale = Locale(identifier: "en_US_POSIX")

            for clip in allClips {
                let dateKey: String
                if let createdAt = clip.createdAt {
                    // Extract YYYY-MM-DD portion
                    let dayPart = String(createdAt.prefix(10))
                    dateKey = (clip.gymId ?? "unknown") + "_" + dayPart
                } else {
                    dateKey = (clip.gymId ?? "unknown") + "_" + clip.rawVideoId
                }
                grouped[dateKey, default: []].append(clip)
            }

            clipsBySession = grouped
            totalSessions = grouped.count

            let successCount = allClips.filter { $0.result == "success" }.count
            if totalClips > 0 {
                let rate = Double(successCount) / Double(totalClips) * 100
                successRate = String(format: "%.0f%%", rate)
            } else {
                successRate = "—"
            }

            // Build recent sessions sorted by date descending
            let gymDb = GymDatabase.shared
            var sessions: [SessionSummary] = []
            for (key, clips) in grouped {
                let parts = key.split(separator: "_", maxSplits: 1)
                let gymId = parts.count > 0 ? String(parts[0]) : "unknown"
                let date = parts.count > 1 ? String(parts[1]) : "—"
                let gymName = gymDb.gyms.first(where: { $0.id == gymId })?.name ?? gymId
                let sc = clips.filter { $0.result == "success" }.count
                let fc = clips.filter { $0.result == "fail" }.count
                sessions.append(SessionSummary(
                    id: key,
                    gymName: gymName,
                    date: date,
                    clipCount: clips.count,
                    successCount: sc,
                    failCount: fc
                ))
            }
            recentSessions = sessions.sorted { $0.date > $1.date }
        } catch {
            // Keep placeholders on error
            print("[MainView] Failed to load home data: \(error)")
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
            statCard(title: "총 세션", value: totalSessions > 0 ? "\(totalSessions)" : "—", icon: "calendar")
            statCard(title: "총 클립", value: totalClips > 0 ? "\(totalClips)" : "—", icon: "film.stack")
            statCard(title: "완등률", value: successRate, icon: "trophy")
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

            if recentSessions.isEmpty {
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
            } else {
                ForEach(recentSessions.prefix(5)) { session in
                    sessionCard(session)
                }
            }
        }
    }

    private func sessionCard(_ session: SessionSummary) -> some View {
        Button {
            // Navigate to ResultView with first clip's rawVideoId as session proxy
            if let clips = clipsBySession[session.id],
               let firstClip = clips.first {
                pushSessionId = firstClip.rawVideoId
            }
        } label: {
            HStack(spacing: 14) {
                // Date icon
                VStack(spacing: 2) {
                    Image(systemName: "calendar")
                        .font(.title3)
                        .foregroundColor(AppColor.accent)
                    Text(formatDateShort(session.date))
                        .font(AppFont.caption)
                        .foregroundColor(.white.opacity(0.6))
                }
                .frame(width: 50)

                VStack(alignment: .leading, spacing: 4) {
                    Text(session.gymName)
                        .font(AppFont.cardTitle)
                        .foregroundColor(.white)

                    HStack(spacing: 12) {
                        Label("\(session.clipCount)개 클립", systemImage: "film")
                            .font(AppFont.caption)
                            .foregroundColor(.white.opacity(0.5))

                        if session.successCount > 0 {
                            Label("\(session.successCount) 완등", systemImage: "checkmark.circle.fill")
                                .font(AppFont.caption)
                                .foregroundColor(AppColor.success)
                        }

                        if session.failCount > 0 {
                            Label("\(session.failCount) 실패", systemImage: "xmark.circle.fill")
                                .font(AppFont.caption)
                                .foregroundColor(AppColor.fail)
                        }
                    }
                }

                Spacer()

                Image(systemName: "chevron.right")
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.3))
            }
            .padding(16)
            .background(AppColor.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 14))
        }
    }

    private func formatDateShort(_ dateString: String) -> String {
        // Input: "2026-03-14" → Output: "3/14"
        let parts = dateString.split(separator: "-")
        guard parts.count >= 3 else { return dateString }
        let month = Int(parts[1]) ?? 0
        let day = Int(parts[2]) ?? 0
        return "\(month)/\(day)"
    }
}
