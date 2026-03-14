import SwiftUI
import AVKit

struct ClipDetailView: View {
    let clip: Clip
    let sessionId: String
    @State private var player: AVPlayer?
    @State private var showCarousel = false
    @State private var isPlaying = false

    private var duration: String {
        guard let start = clip.startTime, let end = clip.endTime else { return "—" }
        let seconds = Int(end - start)
        return String(format: "%d:%02d", seconds / 60, seconds % 60)
    }

    private var tapeColorName: String {
        guard let diff = clip.difficulty else { return "—" }
        if diff.contains("V0") || diff.contains("V1") { return "노랑" }
        if diff.contains("V2") || diff.contains("V3") { return "초록" }
        if diff.contains("V4") || diff.contains("V5") { return "파랑" }
        if diff.contains("V6") || diff.contains("V7") { return "빨강" }
        if diff.contains("V8") { return "검정" }
        return "—"
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                // Video Player
                videoPlayer
                    .aspectRatio(3.0/4.0, contentMode: .fit)
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                    .shadow(color: .black.opacity(0.3), radius: 8, y: 4)
                    .padding(.horizontal)

                // "나의 클립" badge
                if clip.isMe == true {
                    HStack(spacing: 8) {
                        Image(systemName: "person.fill.checkmark")
                            .foregroundStyle(.white)
                        Text("내가 등반한 클립입니다")
                            .font(AppFont.cardTitle)
                            .foregroundStyle(.white)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(Color.blue.gradient)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                    .padding(.horizontal)
                }

                // Metadata Cards (2x2 grid)
                metadataGrid
                    .padding(.horizontal)

                // Action Button
                Button {
                    showCarousel = true
                } label: {
                    Label("캐러셀에 추가", systemImage: "square.grid.2x2")
                }
                .buttonStyle(PrimaryButtonStyle())
                .padding(.horizontal)
                .padding(.bottom, 20)
            }
        }
        .background(AppColor.background)
        .navigationTitle("클립 상세")
        .navigationBarTitleDisplayMode(.inline)
        .navigationDestination(isPresented: $showCarousel) {
            CarouselView(sessionId: sessionId, initialClip: clip)
        }
        .onAppear { setupPlayer() }
        .onDisappear { player?.pause() }
    }

    // MARK: - Video Player

    private var videoPlayer: some View {
        ZStack {
            if let player {
                VideoPlayer(player: player)
            } else {
                Rectangle()
                    .fill(AppColor.cardBackground)
                    .overlay {
                        // Shimmer loading effect
                        VStack(spacing: 12) {
                            ProgressView()
                                .tint(AppColor.accent)
                            Text("버퍼링 중...")
                                .font(AppFont.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
            }
        }
    }

    // MARK: - Metadata Grid

    private var metadataGrid: some View {
        LazyVGrid(columns: [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)], spacing: 12) {
            // 난이도
            metadataCard(
                icon: "chart.bar.fill",
                label: "난이도",
                value: clip.difficulty ?? "—",
                accentColor: AppColor.difficultyColor(clip.difficulty),
                showColorBar: true
            )

            // 결과
            metadataCard(
                icon: clip.result == "success" ? "checkmark.circle.fill" : "xmark.circle.fill",
                label: "결과",
                value: clip.result == "success" ? "완등" : clip.result == "fail" ? "실패" : "—",
                accentColor: clip.result == "success" ? AppColor.success : AppColor.fail
            )

            // 시간
            metadataCard(
                icon: "clock.fill",
                label: "시간",
                value: duration,
                accentColor: AppColor.accent
            )

            // 테이프 색상
            metadataCard(
                icon: "paintpalette.fill",
                label: "테이프",
                value: tapeColorName,
                accentColor: AppColor.difficultyColor(clip.difficulty),
                showColorSwatch: true
            )
        }
    }

    private func metadataCard(
        icon: String,
        label: String,
        value: String,
        accentColor: Color,
        showColorBar: Bool = false,
        showColorSwatch: Bool = false
    ) -> some View {
        HStack(spacing: 0) {
            // Left accent bar for difficulty
            if showColorBar {
                RoundedRectangle(cornerRadius: 2)
                    .fill(accentColor)
                    .frame(width: 4)
                    .padding(.vertical, 8)
            }

            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: icon)
                        .font(.system(size: 14))
                        .foregroundStyle(accentColor)
                    Text(label)
                        .font(AppFont.caption)
                        .foregroundStyle(.secondary)
                }

                HStack(spacing: 6) {
                    Text(value)
                        .font(AppFont.sectionTitle)
                        .foregroundStyle(.primary)

                    if showColorSwatch {
                        Circle()
                            .fill(accentColor)
                            .frame(width: 14, height: 14)
                            .overlay(Circle().stroke(.white.opacity(0.3), lineWidth: 1))
                    }
                }
            }
            .padding(.horizontal, showColorBar ? 10 : 14)
            .padding(.vertical, 14)

            Spacer()
        }
        .background(AppColor.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Setup

    private func setupPlayer() {
        let urlString = "\(Config.baseURLString)/clips/\(clip.id)/video"
        guard let url = URL(string: urlString) else { return }

        let asset = AVURLAsset(url: url, options: [
            "AVURLAssetHTTPHeaderFieldsKey": [
                "Authorization": "Bearer \(KeychainHelper.load(.accessToken) ?? "")"
            ]
        ])
        let item = AVPlayerItem(asset: asset)
        player = AVPlayer(playerItem: item)
    }
}
