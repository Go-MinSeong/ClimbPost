import SwiftUI
import AVKit

struct ClipDetailView: View {
    let clip: Clip
    let sessionId: String
    @State private var player: AVPlayer?
    @State private var showCarousel = false

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                // Video Player
                videoPlayer
                    .aspectRatio(3/4, contentMode: .fit)
                    .clipShape(RoundedRectangle(cornerRadius: 12))

                // Metadata
                metadataSection

                // Actions
                Button {
                    showCarousel = true
                } label: {
                    Label("Add to Carousel", systemImage: "square.grid.2x2")
                        .font(.headline)
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.blue)
                        .foregroundColor(.white)
                        .cornerRadius(12)
                }
                .padding(.horizontal)
            }
        }
        .navigationTitle("Clip Detail")
        .navigationBarTitleDisplayMode(.inline)
        .navigationDestination(isPresented: $showCarousel) {
            CarouselView(sessionId: sessionId, initialClip: clip)
        }
        .onAppear { setupPlayer() }
        .onDisappear { player?.pause() }
    }

    private var videoPlayer: some View {
        Group {
            if let player {
                VideoPlayer(player: player)
            } else {
                Rectangle()
                    .fill(Color(.tertiarySystemFill))
                    .overlay(ProgressView())
            }
        }
    }

    private var metadataSection: some View {
        VStack(spacing: 12) {
            HStack {
                metadataItem(title: "Difficulty", value: clip.difficulty ?? "—")
                Spacer()
                metadataItem(title: "Result", value: (clip.result ?? "—").capitalized)
                Spacer()
                metadataItem(title: "Duration", value: formatDuration())
            }
            .padding(.horizontal)

            if clip.isMe == true {
                HStack {
                    Image(systemName: "person.fill.checkmark")
                        .foregroundStyle(.blue)
                    Text("This is you")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private func metadataItem(title: String, value: String) -> some View {
        VStack(spacing: 4) {
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.headline)
        }
    }

    private func formatDuration() -> String {
        guard let start = clip.startTime, let end = clip.endTime else { return "—" }
        let seconds = Int(end - start)
        return String(format: "%d:%02d", seconds / 60, seconds % 60)
    }

    private func setupPlayer() {
        let urlString = "\(Config.baseURLString)/clips/\(clip.id)/video"
        guard let url = URL(string: urlString) else { return }

        var request = URLRequest(url: url)
        if let token = KeychainHelper.load(.accessToken) {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let asset = AVURLAsset(url: url, options: [
            "AVURLAssetHTTPHeaderFieldsKey": [
                "Authorization": "Bearer \(KeychainHelper.load(.accessToken) ?? "")"
            ]
        ])
        let item = AVPlayerItem(asset: asset)
        player = AVPlayer(playerItem: item)
    }
}
