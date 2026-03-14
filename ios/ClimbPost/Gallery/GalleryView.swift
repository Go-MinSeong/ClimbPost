import SwiftUI
import Photos

struct GalleryView: View {
    @StateObject private var galleryService = GalleryService()
    @State private var selectedIDs: Set<String> = []
    @State private var showUpload = false

    var allSelected: Bool {
        !galleryService.detectedVideos.isEmpty &&
        selectedIDs.count == galleryService.detectedVideos.count
    }

    var body: some View {
        VStack(spacing: 0) {
            if galleryService.isScanning {
                Spacer()
                ProgressView("Scanning for climbing videos...")
                Spacer()
            } else if galleryService.authorizationStatus == .denied ||
                      galleryService.authorizationStatus == .restricted {
                permissionDeniedView
            } else if galleryService.detectedVideos.isEmpty {
                emptyStateView
            } else {
                videoListView
            }
        }
        .navigationTitle("Today's Videos")
        .task {
            await galleryService.requestAuthorization()
            await galleryService.scanForClimbingVideos()
            // Select all by default
            selectedIDs = Set(galleryService.detectedVideos.map(\.id))
        }
        .navigationDestination(isPresented: $showUpload) {
            UploadView(
                videos: galleryService.detectedVideos.filter { selectedIDs.contains($0.id) }
            )
        }
    }

    // MARK: - Subviews

    private var videoListView: some View {
        VStack(spacing: 0) {
            // Header with select all toggle
            HStack {
                Text("\(galleryService.detectedVideos.count) climbing videos found")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                Spacer()
                Button(allSelected ? "Deselect All" : "Select All") {
                    if allSelected {
                        selectedIDs.removeAll()
                    } else {
                        selectedIDs = Set(galleryService.detectedVideos.map(\.id))
                    }
                }
                .font(.subheadline)
            }
            .padding(.horizontal)
            .padding(.vertical, 8)

            List(galleryService.detectedVideos) { video in
                VideoRow(
                    video: video,
                    isSelected: selectedIDs.contains(video.id)
                )
                .contentShape(Rectangle())
                .onTapGesture {
                    if selectedIDs.contains(video.id) {
                        selectedIDs.remove(video.id)
                    } else {
                        selectedIDs.insert(video.id)
                    }
                }
            }
            .listStyle(.plain)

            // Upload button
            Button {
                showUpload = true
            } label: {
                Text("Upload \(selectedIDs.count) Videos")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(selectedIDs.isEmpty ? Color.gray : Color.blue)
                    .foregroundColor(.white)
                    .cornerRadius(12)
            }
            .disabled(selectedIDs.isEmpty)
            .padding()
        }
    }

    private var emptyStateView: some View {
        VStack(spacing: 16) {
            Spacer()
            Image(systemName: "video.slash")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
            Text("No climbing videos found")
                .font(.title3.bold())
            Text("Record videos at a climbing gym today,\nthen come back to upload them.")
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Button("Scan Again") {
                Task { await galleryService.scanForClimbingVideos() }
            }
            .buttonStyle(.bordered)
            Spacer()
        }
        .padding()
    }

    private var permissionDeniedView: some View {
        VStack(spacing: 16) {
            Spacer()
            Image(systemName: "photo.on.rectangle.angled")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
            Text("Photo Library Access Required")
                .font(.title3.bold())
            Text("ClimbPost needs access to your photos to find climbing videos. Please enable access in Settings.")
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Button("Open Settings") {
                if let url = URL(string: UIApplication.openSettingsURLString) {
                    UIApplication.shared.open(url)
                }
            }
            .buttonStyle(.borderedProminent)
            Spacer()
        }
        .padding()
    }
}

// MARK: - Video Row

struct VideoRow: View {
    let video: DetectedVideo
    let isSelected: Bool

    @State private var thumbnail: UIImage?

    var body: some View {
        HStack(spacing: 12) {
            // Checkbox
            Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                .foregroundStyle(isSelected ? .blue : .secondary)
                .font(.title3)

            // Thumbnail
            Group {
                if let thumbnail {
                    Image(uiImage: thumbnail)
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                } else {
                    Rectangle()
                        .fill(Color.gray.opacity(0.2))
                        .overlay {
                            Image(systemName: "video.fill")
                                .foregroundStyle(.secondary)
                        }
                }
            }
            .frame(width: 80, height: 60)
            .cornerRadius(8)
            .clipped()

            // Info
            VStack(alignment: .leading, spacing: 4) {
                Text(video.gym.name)
                    .font(.body.bold())
                HStack(spacing: 8) {
                    Label(video.formattedDuration, systemImage: "clock")
                    Label(video.creationDate.formatted(date: .omitted, time: .shortened),
                          systemImage: "calendar")
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }

            Spacer()
        }
        .padding(.vertical, 4)
        .task {
            await loadThumbnail()
        }
    }

    private func loadThumbnail() async {
        let manager = PHImageManager.default()
        let options = PHImageRequestOptions()
        options.isSynchronous = false
        options.deliveryMode = .opportunistic
        options.resizeMode = .fast

        let size = CGSize(width: 160, height: 120)
        let result: UIImage? = await withCheckedContinuation { continuation in
            manager.requestImage(
                for: video.asset,
                targetSize: size,
                contentMode: .aspectFill,
                options: options
            ) { image, _ in
                continuation.resume(returning: image)
            }
        }
        await MainActor.run { thumbnail = result }
    }
}
