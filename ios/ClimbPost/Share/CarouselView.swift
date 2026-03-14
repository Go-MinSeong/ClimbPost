import SwiftUI

struct CarouselView: View {
    let sessionId: String
    let initialClip: Clip?

    @StateObject private var viewModel: ResultViewModel
    @State private var selectedClipIds: [String] = []
    @State private var isSharing = false
    @State private var shareError: String?

    init(sessionId: String, initialClip: Clip? = nil) {
        self.sessionId = sessionId
        self.initialClip = initialClip
        _viewModel = StateObject(wrappedValue: ResultViewModel(sessionId: sessionId))
    }

    var selectedClips: [Clip] {
        selectedClipIds.compactMap { id in
            viewModel.clips.first { $0.id == id }
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Preview of selected clips
            if !selectedClips.isEmpty {
                selectedPreview
            }

            // Clip selection list
            clipSelectionList

            // Share button
            shareButton
        }
        .navigationTitle("Carousel")
        .navigationBarTitleDisplayMode(.inline)
        .alert("Share Error", isPresented: .init(
            get: { shareError != nil },
            set: { if !$0 { shareError = nil } }
        )) {
            Button("OK") { shareError = nil }
        } message: {
            Text(shareError ?? "")
        }
        .task {
            await viewModel.fetchClips()
            if let clip = initialClip, !selectedClipIds.contains(clip.id) {
                selectedClipIds.append(clip.id)
            }
        }
    }

    // MARK: - Selected Preview

    private var selectedPreview: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Selected (\(selectedClips.count))")
                .font(.subheadline.bold())
                .padding(.horizontal)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(selectedClips) { clip in
                        selectedClipThumbnail(clip)
                    }
                }
                .padding(.horizontal)
            }
        }
        .padding(.vertical, 12)
        .background(Color(.systemGroupedBackground))
    }

    private func selectedClipThumbnail(_ clip: Clip) -> some View {
        ZStack(alignment: .topTrailing) {
            if let urlString = clip.thumbnailUrl, let url = URL(string: urlString) {
                AsyncImage(url: url) { image in
                    image.resizable().aspectRatio(3/4, contentMode: .fill)
                } placeholder: {
                    Color(.tertiarySystemFill)
                }
                .frame(width: 60, height: 80)
                .clipShape(RoundedRectangle(cornerRadius: 6))
            } else {
                RoundedRectangle(cornerRadius: 6)
                    .fill(Color(.tertiarySystemFill))
                    .frame(width: 60, height: 80)
                    .overlay(Image(systemName: "film").foregroundStyle(.secondary))
            }

            // Order badge
            if let index = selectedClipIds.firstIndex(of: clip.id) {
                Text("\(index + 1)")
                    .font(.caption2.bold())
                    .foregroundStyle(.white)
                    .frame(width: 18, height: 18)
                    .background(Color.blue, in: Circle())
                    .offset(x: 4, y: -4)
            }
        }
    }

    // MARK: - Clip Selection List

    private var clipSelectionList: some View {
        List {
            ForEach(viewModel.clips) { clip in
                clipRow(clip)
                    .contentShape(Rectangle())
                    .onTapGesture { toggleSelection(clip) }
            }
            .onMove { source, destination in
                // Only allow reordering of selected items in the context of the full list
                selectedClipIds.move(fromOffsets: source, toOffset: destination)
            }
        }
        .listStyle(.plain)
    }

    private func clipRow(_ clip: Clip) -> some View {
        HStack(spacing: 12) {
            // Checkbox
            Image(systemName: selectedClipIds.contains(clip.id) ? "checkmark.circle.fill" : "circle")
                .foregroundStyle(selectedClipIds.contains(clip.id) ? .blue : .secondary)
                .font(.title3)

            // Thumbnail
            if let urlString = clip.thumbnailUrl, let url = URL(string: urlString) {
                AsyncImage(url: url) { image in
                    image.resizable().aspectRatio(3/4, contentMode: .fill)
                } placeholder: {
                    Color(.tertiarySystemFill)
                }
                .frame(width: 48, height: 64)
                .clipShape(RoundedRectangle(cornerRadius: 4))
            }

            // Info
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    if let difficulty = clip.difficulty {
                        Text(difficulty)
                            .font(.subheadline.bold())
                    }
                    if let result = clip.result {
                        Image(systemName: result == "success" ? "checkmark.circle.fill" : "xmark.circle.fill")
                            .foregroundStyle(result == "success" ? .green : .red)
                            .font(.caption)
                    }
                }
                if let start = clip.startTime, let end = clip.endTime {
                    let seconds = Int(end - start)
                    Text(String(format: "%d:%02d", seconds / 60, seconds % 60))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Spacer()

            // Drag handle hint for selected items
            if selectedClipIds.contains(clip.id) {
                Image(systemName: "line.3.horizontal")
                    .foregroundStyle(.secondary)
            }
        }
    }

    // MARK: - Share Button

    private var shareButton: some View {
        Button {
            shareToInstagram()
        } label: {
            HStack {
                Image(systemName: "square.and.arrow.up")
                Text("Share to Instagram")
            }
            .font(.headline)
            .frame(maxWidth: .infinity)
            .padding()
            .background(selectedClips.isEmpty ? Color.gray : Color.blue)
            .foregroundColor(.white)
            .cornerRadius(12)
        }
        .disabled(selectedClips.isEmpty || isSharing)
        .padding()
    }

    // MARK: - Actions

    private func toggleSelection(_ clip: Clip) {
        if let index = selectedClipIds.firstIndex(of: clip.id) {
            selectedClipIds.remove(at: index)
        } else {
            selectedClipIds.append(clip.id)
        }
    }

    private func shareToInstagram() {
        isSharing = true
        Task {
            do {
                let videoURLs = try await ShareService.shared.prepareClipVideos(
                    clips: selectedClips,
                    baseURLString: Config.baseURLString
                )
                await MainActor.run {
                    ShareService.shared.presentShareSheet(videoURLs: videoURLs)
                    isSharing = false
                }
            } catch {
                await MainActor.run {
                    shareError = error.localizedDescription
                    isSharing = false
                }
            }
        }
    }
}
