import SwiftUI

struct AnalysisWaitingView: View {
    let sessionId: String

    @State private var status: String = "pending"
    @State private var serverProgress: Double = 0
    @State private var displayProgress: Double = 0
    @State private var showResult = false
    @State private var errorMessage: String?
    @State private var isPulsing = false
    @State private var stageIndex = 0

    let pollTimer = Timer.publish(every: 3, on: .main, in: .common).autoconnect()
    let fakeTimer = Timer.publish(every: 0.8, on: .main, in: .common).autoconnect()

    private let stages = [
        "영상에서 클라이밍 구간을 찾고 있어요",
        "성공/실패를 분류하고 있어요",
        "난이도를 분석하고 있어요",
        "등반자를 식별하고 있어요",
        "인스타그램용으로 편집하고 있어요",
        "거의 다 됐어요!",
    ]

    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            // Circular progress with mountain icon
            ZStack {
                Circle()
                    .stroke(Color.white.opacity(0.08), lineWidth: 8)
                    .frame(width: 180, height: 180)

                Circle()
                    .trim(from: 0, to: displayProgress / 100)
                    .stroke(
                        status == "failed" ? AppColor.fail : AppColor.accent,
                        style: StrokeStyle(lineWidth: 8, lineCap: .round)
                    )
                    .frame(width: 180, height: 180)
                    .rotationEffect(.degrees(-90))
                    .animation(.easeInOut(duration: 0.5), value: displayProgress)

                if status == "completed" {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 72))
                        .foregroundStyle(AppColor.success)
                        .transition(.scale.combined(with: .opacity))
                } else if status == "failed" {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 72))
                        .foregroundStyle(AppColor.fail)
                } else {
                    Image(systemName: "mountain.2.fill")
                        .font(.system(size: 56))
                        .foregroundStyle(AppColor.accent)
                        .scaleEffect(isPulsing ? 1.08 : 0.95)
                }
            }

            // Title
            Text(titleText)
                .font(AppFont.heroTitle)
                .foregroundStyle(.white)

            // Progress percentage
            if status != "failed" && status != "completed" {
                Text("\(Int(displayProgress))%")
                    .font(.system(size: 32, weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(AppColor.accent)
                    .contentTransition(.numericText())
            }

            // Stage description
            Text(currentStageText)
                .font(AppFont.cardTitle)
                .foregroundStyle(.white.opacity(0.6))
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)
                .animation(.easeInOut(duration: 0.3), value: stageIndex)
                .id(stageIndex)

            Spacer()

            // Bottom
            if status == "failed" {
                Button("다시 시도") {
                    errorMessage = nil
                    status = "pending"
                    displayProgress = 0
                    serverProgress = 0
                    Task { await checkStatus() }
                }
                .buttonStyle(PrimaryButtonStyle())
                .padding(.horizontal, 40)
            } else if status != "completed" {
                VStack(spacing: 8) {
                    // Stage dots
                    HStack(spacing: 6) {
                        ForEach(0..<stages.count, id: \.self) { i in
                            Circle()
                                .fill(i <= stageIndex ? AppColor.accent : Color.white.opacity(0.15))
                                .frame(width: 6, height: 6)
                                .animation(.easeInOut(duration: 0.3), value: stageIndex)
                        }
                    }

                    Text("앱을 닫아도 분석은 계속됩니다")
                        .font(AppFont.caption)
                        .foregroundStyle(.white.opacity(0.3))
                }
            }

            Spacer().frame(height: 40)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AppColor.background.ignoresSafeArea())
        .navigationTitle("분석 중")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(AppColor.background, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .onAppear {
            withAnimation(.easeInOut(duration: 1.2).repeatForever(autoreverses: true)) {
                isPulsing = true
            }
        }
        .onReceive(pollTimer) { _ in
            guard status != "completed" && status != "failed" else { return }
            Task { await checkStatus() }
        }
        .onReceive(fakeTimer) { _ in
            guard status != "completed" && status != "failed" else { return }
            // Smoothly increment display progress toward server progress
            // but also fake gradual progress so it doesn't feel stuck
            let target = max(serverProgress, min(displayProgress + 1.5, 95))
            withAnimation(.easeOut(duration: 0.5)) {
                displayProgress = min(target, 99)
            }
            // Advance stage based on display progress
            let newStage = min(Int(displayProgress / 18), stages.count - 1)
            if newStage != stageIndex {
                stageIndex = newStage
            }
        }
        .task {
            await checkStatus()
        }
        .navigationDestination(isPresented: $showResult) {
            ResultView(sessionId: sessionId)
        }
    }

    private var titleText: String {
        switch status {
        case "completed": return "분석 완료!"
        case "failed": return "분석 실패"
        default: return "분석 중..."
        }
    }

    private var currentStageText: String {
        if status == "completed" { return "결과를 불러오는 중..." }
        if status == "failed" { return errorMessage ?? "분석에 실패했습니다" }
        return stages[min(stageIndex, stages.count - 1)]
    }

    private func checkStatus() async {
        do {
            let result = try await APIClient.shared.getAnalysisStatus(sessionId: sessionId)
            withAnimation {
                serverProgress = result.progressPct
                status = result.status
            }
            if result.status == "completed" {
                withAnimation {
                    displayProgress = 100
                    isPulsing = false
                }
                try? await Task.sleep(nanoseconds: 1_200_000_000)
                showResult = true
            } else if result.status == "failed" {
                errorMessage = "분석에 실패했습니다. 다시 시도해 주세요."
            }
        } catch {
            // Transient failures — keep polling
        }
    }
}
