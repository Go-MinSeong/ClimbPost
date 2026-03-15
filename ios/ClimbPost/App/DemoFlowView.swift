import SwiftUI
import AVKit
import os.log

private let demoLogger = Logger(subsystem: "com.climbpost.app", category: "Demo")

struct DemoFlowView: View {
    @State private var player: AVPlayer?
    @State private var statusText = "다운로드 중..."
    @State private var errorText: String?

    private let testVideoURL = "http://127.0.0.1:8000/storage/edited/6b2ae75b-5120-4719-811d-4cfdafe5b6dc/56e0802dfa9f_edited.mp4"

    var body: some View {
        VStack(spacing: 16) {
            Text("비디오 재생 테스트")
                .font(AppFont.sectionTitle)
                .foregroundColor(.white)

            if let player {
                VideoPlayer(player: player)
                    .frame(height: 400)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
            } else {
                RoundedRectangle(cornerRadius: 12)
                    .fill(AppColor.cardBackground)
                    .frame(height: 400)
                    .overlay {
                        VStack {
                            ProgressView()
                                .tint(AppColor.accent)
                            Text(statusText)
                                .font(AppFont.caption)
                                .foregroundStyle(.white.opacity(0.6))
                        }
                    }
            }

            if let errorText {
                Text(errorText)
                    .font(.system(size: 11))
                    .foregroundColor(.red)
                    .padding(.horizontal)
            }

            Text(statusText)
                .font(AppFont.caption)
                .foregroundColor(.white.opacity(0.5))
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AppColor.background.ignoresSafeArea())
        .task {
            await downloadAndPlay()
        }
    }

    private func downloadAndPlay() async {
        guard let remoteURL = URL(string: testVideoURL) else {
            statusText = "잘못된 URL"
            return
        }

        statusText = "서버에서 다운로드 중..."
        demoLogger.error("Downloading: \(testVideoURL)")

        do {
            let (localURL, response) = try await URLSession.shared.download(from: remoteURL)
            let httpResponse = response as? HTTPURLResponse
            demoLogger.error("Downloaded: HTTP \(httpResponse?.statusCode ?? 0), file: \(localURL.path)")
            statusText = "다운로드 완료 (HTTP \(httpResponse?.statusCode ?? 0))"

            // Move to a permanent temp location with .mp4 extension
            let dest = FileManager.default.temporaryDirectory.appendingPathComponent("test_clip.mp4")
            try? FileManager.default.removeItem(at: dest)
            try FileManager.default.moveItem(at: localURL, to: dest)

            demoLogger.error("Playing local file: \(dest.path)")
            statusText = "재생 중..."

            await MainActor.run {
                let p = AVPlayer(url: dest)
                player = p
                p.play()
            }
        } catch {
            demoLogger.error("Download failed: \(error.localizedDescription)")
            statusText = "실패"
            errorText = error.localizedDescription
        }
    }
}
