import SwiftUI

struct UploadView: View {
    let videos: [DetectedVideo]

    @StateObject private var uploadState = UploadState()
    @Environment(\.dismiss) private var dismiss
    @State private var showResult = false

    var body: some View {
        VStack(spacing: 24) {
            if uploadState.isComplete {
                completedView
            } else if uploadState.isUploading {
                uploadingView
            } else if let error = uploadState.errorMessage {
                errorView(error)
            } else {
                Spacer()
                ProgressView("업로드 준비 중...")
                    .foregroundStyle(.white)
                Spacer()
            }
        }
        .padding()
        .background(AppColor.background.ignoresSafeArea())
        .navigationTitle("업로드")
        .navigationBarBackButtonHidden(uploadState.isUploading)
        .task {
            await UploadService.shared.uploadVideos(videos, state: uploadState)
        }
    }

    // MARK: - Uploading

    private var uploadingView: some View {
        VStack(spacing: 20) {
            Spacer()

            // Circular progress with percentage
            ZStack {
                // Background circle
                Circle()
                    .stroke(AppColor.cardBackground, lineWidth: 8)
                    .frame(width: 140, height: 140)

                // Progress arc
                Circle()
                    .trim(from: 0, to: uploadState.progress)
                    .stroke(AppColor.accent, style: StrokeStyle(lineWidth: 8, lineCap: .round))
                    .frame(width: 140, height: 140)
                    .rotationEffect(.degrees(-90))
                    .animation(.easeInOut(duration: 0.3), value: uploadState.progress)

                // Percentage text
                Text("\(Int(uploadState.progress * 100))%")
                    .font(.system(size: 36, weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(.white)

                // Pulsing upload icon
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 24))
                    .foregroundStyle(AppColor.accent)
                    .offset(y: -90)
                    .modifier(PulseModifier())
            }

            Text("영상 업로드 중")
                .font(AppFont.sectionTitle)
                .foregroundStyle(.white)

            Text("\(uploadState.currentFileIndex) / \(uploadState.totalFiles) 파일")
                .font(AppFont.caption)
                .foregroundStyle(.white.opacity(0.5))

            // Per-file progress list
            VStack(alignment: .leading, spacing: 6) {
                ForEach(videos) { video in
                    let fileProg = uploadState.fileProgress[video.id] ?? 0
                    HStack(spacing: 10) {
                        Image(systemName: fileProg >= 1.0 ? "checkmark.circle.fill" : "circle")
                            .foregroundStyle(fileProg >= 1.0 ? AppColor.success : .white.opacity(0.3))
                            .font(.system(size: 14))

                        Text(video.gym.name)
                            .font(AppFont.caption)
                            .foregroundStyle(.white.opacity(0.8))
                            .lineLimit(1)

                        Spacer()

                        if fileProg >= 1.0 {
                            Image(systemName: "checkmark")
                                .font(.system(size: 10, weight: .bold))
                                .foregroundStyle(AppColor.success)
                        } else if fileProg > 0 {
                            // Small progress bar
                            ZStack(alignment: .leading) {
                                Capsule()
                                    .fill(AppColor.cardBackground)
                                    .frame(width: 50, height: 4)
                                Capsule()
                                    .fill(AppColor.accent)
                                    .frame(width: 50 * fileProg, height: 4)
                                    .animation(.easeInOut(duration: 0.2), value: fileProg)
                            }
                            Text("\(Int(fileProg * 100))%")
                                .font(.system(size: 10, weight: .medium, design: .rounded))
                                .monospacedDigit()
                                .foregroundStyle(.white.opacity(0.5))
                                .frame(width: 30, alignment: .trailing)
                        }
                    }
                }
            }
            .padding(14)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(AppColor.cardBackground)
            )

            Text("앱을 종료해도 업로드가 계속됩니다")
                .font(AppFont.caption)
                .foregroundStyle(.white.opacity(0.4))

            Spacer()
        }
    }

    // MARK: - Completed

    private var completedView: some View {
        VStack(spacing: 20) {
            Spacer()

            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 72))
                .foregroundStyle(AppColor.success)
                .scaleEffect(uploadState.isComplete ? 1.0 : 0.3)
                .animation(.spring(response: 0.5, dampingFraction: 0.6), value: uploadState.isComplete)

            Text("업로드 완료!")
                .font(AppFont.heroTitle)
                .foregroundStyle(.white)

            Text("\(videos.count)개 영상이 업로드되었습니다.\n분석이 시작되었습니다 — 알림을 보내드릴게요.")
                .font(AppFont.caption)
                .foregroundStyle(.white.opacity(0.6))
                .multilineTextAlignment(.center)

            Button("결과 보기") {
                showResult = true
            }
            .buttonStyle(PrimaryButtonStyle())
            .frame(width: 200)
            .padding(.top, 8)

            Button("홈으로") {
                dismiss()
            }
            .foregroundColor(.white.opacity(0.6))

            Spacer()
        }
        .navigationDestination(isPresented: $showResult) {
            if let sessionId = uploadState.sessionId {
                ResultView(sessionId: sessionId)
            }
        }
    }

    // MARK: - Error

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 20) {
            Spacer()

            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 56))
                .foregroundStyle(AppColor.fail)

            Text("업로드 실패")
                .font(AppFont.sectionTitle)
                .foregroundStyle(.white)

            Text(message)
                .font(AppFont.caption)
                .foregroundStyle(.white.opacity(0.6))
                .multilineTextAlignment(.center)

            HStack(spacing: 16) {
                Button("돌아가기") {
                    dismiss()
                }
                .buttonStyle(PrimaryButtonStyle(isEnabled: false))

                Button("다시 시도") {
                    uploadState.reset()
                    Task {
                        await UploadService.shared.uploadVideos(videos, state: uploadState)
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
            }

            Spacer()
        }
    }
}

// MARK: - Pulse Animation Modifier

private struct PulseModifier: ViewModifier {
    @State private var isPulsing = false

    func body(content: Content) -> some View {
        content
            .scaleEffect(isPulsing ? 1.15 : 1.0)
            .opacity(isPulsing ? 0.7 : 1.0)
            .animation(
                .easeInOut(duration: 1.0).repeatForever(autoreverses: true),
                value: isPulsing
            )
            .onAppear { isPulsing = true }
    }
}
