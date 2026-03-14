import SwiftUI

struct AnalysisWaitingView: View {
    let sessionId: String

    @State private var status: String = "pending"
    @State private var progressPct: Double = 0
    @State private var showResult = false
    @State private var errorMessage: String?
    @State private var isPulsing = false

    let timer = Timer.publish(every: 3, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            // Mountain icon with pulse animation
            ZStack {
                // Circular progress gauge
                Circle()
                    .stroke(AppColor.cardBackground, lineWidth: 8)
                    .frame(width: 160, height: 160)

                Circle()
                    .trim(from: 0, to: progressPct / 100)
                    .stroke(
                        status == "failed" ? AppColor.fail : AppColor.accent,
                        style: StrokeStyle(lineWidth: 8, lineCap: .round)
                    )
                    .frame(width: 160, height: 160)
                    .rotationEffect(.degrees(-90))
                    .animation(.easeInOut(duration: 0.6), value: progressPct)

                if status == "completed" {
                    // Checkmark on completion
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 64))
                        .foregroundStyle(AppColor.success)
                        .transition(.scale.combined(with: .opacity))
                } else if status == "failed" {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 64))
                        .foregroundStyle(AppColor.fail)
                } else {
                    // Mountain icon with pulse
                    Image(systemName: "mountain.2.fill")
                        .font(.system(size: 56))
                        .foregroundStyle(AppColor.accent)
                        .scaleEffect(isPulsing ? 1.1 : 0.9)
                        .animation(
                            .easeInOut(duration: 1.2).repeatForever(autoreverses: true),
                            value: isPulsing
                        )
                }
            }

            // Title
            Text(titleText)
                .font(AppFont.heroTitle)
                .foregroundStyle(.white)
                .animation(.easeInOut, value: status)

            // Progress percentage
            if status != "failed" {
                Text("\(Int(progressPct))%")
                    .font(.system(size: 28, weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(AppColor.accent)
            }

            // Status message
            Text(statusMessage)
                .font(AppFont.caption)
                .foregroundStyle(.white.opacity(0.6))
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)
                .animation(.easeInOut, value: status)

            Spacer()

            // Bottom hint or retry button
            if status == "failed" {
                Button("다시 시도") {
                    errorMessage = nil
                    status = "pending"
                    progressPct = 0
                    Task { await checkStatus() }
                }
                .buttonStyle(PrimaryButtonStyle())
                .padding(.horizontal, 40)
            } else if status != "completed" {
                Text("앱을 닫아도 분석은 계속됩니다.\n완료되면 알림을 보내드릴게요.")
                    .font(AppFont.caption)
                    .foregroundStyle(.white.opacity(0.35))
                    .multilineTextAlignment(.center)
            }

            Spacer().frame(height: 40)
        }
        .background(AppColor.background.ignoresSafeArea())
        .navigationTitle("분석 중")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            isPulsing = true
        }
        .onReceive(timer) { _ in
            guard status != "completed" && status != "failed" else { return }
            Task { await checkStatus() }
        }
        .task {
            await checkStatus()
        }
        .navigationDestination(isPresented: $showResult) {
            ResultView(sessionId: sessionId)
        }
    }

    // MARK: - Status Text

    private var titleText: String {
        switch status {
        case "completed": return "분석 완료!"
        case "failed": return "분석 실패"
        default: return "분석 중..."
        }
    }

    private var statusMessage: String {
        switch status {
        case "pending":
            return "분석 대기 중..."
        case "analyzing", "processing":
            return "클라이밍 구간을 분석하고 있어요"
        case "completed":
            return "분석 완료! 결과를 불러오는 중..."
        case "failed":
            return errorMessage ?? "분석에 실패했습니다. 다시 시도해 주세요."
        default:
            return "분석을 준비하고 있어요..."
        }
    }

    // MARK: - Polling

    private func checkStatus() async {
        do {
            let result = try await APIClient.shared.getAnalysisStatus(sessionId: sessionId)
            withAnimation {
                self.progressPct = result.progressPct
                self.status = result.status
            }
            if result.status == "completed" {
                // Auto-navigate after 1 second
                try? await Task.sleep(nanoseconds: 1_000_000_000)
                showResult = true
            } else if result.status == "failed" {
                errorMessage = "분석에 실패했습니다. 다시 시도해 주세요."
            }
        } catch {
            // Don't show error on transient network failures — just retry next poll
        }
    }
}
