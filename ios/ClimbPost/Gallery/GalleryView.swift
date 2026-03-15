import SwiftUI
import Photos

struct GalleryView: View {
    @StateObject private var galleryService = GalleryService()
    @State private var selectedIDs: Set<String> = []
    @State private var showUpload = false
    @State private var showUploadConfirm = false

    var allSelected: Bool {
        !galleryService.detectedVideos.isEmpty &&
        selectedIDs.count == galleryService.detectedVideos.count
    }

    var body: some View {
        VStack(spacing: 0) {
            if galleryService.isScanning {
                Spacer()
                ProgressView("영상을 검색하는 중...")
                    .foregroundStyle(.white)
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
        .background(AppColor.background.ignoresSafeArea())
        .navigationTitle("최근 클라이밍 영상")
        .toolbarBackground(AppColor.background, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .onAppear {
            guard !galleryService.isScanning && galleryService.detectedVideos.isEmpty else { return }
            Task {
                await galleryService.requestAuthorization()
                await galleryService.scanForClimbingVideos()
                selectedIDs = Set(galleryService.detectedVideos.map(\.id))
            }
        }
        .navigationDestination(isPresented: $showUpload) {
            UploadView(
                videos: galleryService.detectedVideos.filter { selectedIDs.contains($0.id) }
            )
        }
        .alert("영상 업로드", isPresented: $showUploadConfirm) {
            Button("업로드 시작", role: .none) {
                showUpload = true
            }
            Button("취소", role: .cancel) { }
        } message: {
            Text("\(selectedIDs.count)개 영상을 서버에 업로드합니다.\nWi-Fi 연결을 권장합니다.")
        }
    }

    // MARK: - Subviews

    private var videoListView: some View {
        VStack(spacing: 0) {
            // Header with count and select-all toggle
            HStack {
                Text("\(galleryService.detectedVideos.count)개의 영상을 찾았습니다")
                    .font(AppFont.caption)
                    .foregroundStyle(.white.opacity(0.6))
                Spacer()
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        if allSelected {
                            selectedIDs.removeAll()
                        } else {
                            selectedIDs = Set(galleryService.detectedVideos.map(\.id))
                        }
                    }
                } label: {
                    Text(allSelected ? "전체 해제" : "전체 선택")
                        .font(AppFont.caption)
                        .foregroundStyle(AppColor.accent)
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 10)

            ScrollView {
                LazyVStack(spacing: 8) {
                    ForEach(galleryService.detectedVideos) { video in
                        VideoRow(
                            video: video,
                            isSelected: selectedIDs.contains(video.id)
                        )
                        .contentShape(Rectangle())
                        .onTapGesture {
                            withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                                if selectedIDs.contains(video.id) {
                                    selectedIDs.remove(video.id)
                                } else {
                                    selectedIDs.insert(video.id)
                                }
                            }
                        }
                    }
                }
                .padding(.horizontal)
            }

            // Upload button
            VStack(spacing: 0) {
                Divider().overlay(Color.white.opacity(0.1))
                Button {
                    showUploadConfirm = true
                } label: {
                    HStack(spacing: 8) {
                        if selectedIDs.isEmpty {
                            Text("영상을 선택하세요")
                        } else {
                            Text("\(selectedIDs.count)개 영상 업로드")
                            Image(systemName: "arrow.up.right")
                        }
                    }
                }
                .buttonStyle(PrimaryButtonStyle(isEnabled: !selectedIDs.isEmpty))
                .disabled(selectedIDs.isEmpty)
                .padding()
            }
        }
    }

    private var emptyStateView: some View {
        VStack(spacing: 16) {
            Spacer()
            Image(systemName: "figure.climbing")
                .font(.system(size: 56))
                .foregroundStyle(AppColor.accent.opacity(0.6))

            Text("오늘 촬영한 영상이 없습니다")
                .font(AppFont.sectionTitle)
                .foregroundStyle(.white)

            Text("암장에서 영상을 촬영한 후\n다시 스캔해 보세요")
                .font(AppFont.caption)
                .foregroundStyle(.white.opacity(0.5))
                .multilineTextAlignment(.center)

            Button("다시 스캔") {
                Task { await galleryService.scanForClimbingVideos() }
            }
            .buttonStyle(PrimaryButtonStyle())
            .frame(width: 160)
            .padding(.top, 8)

            Spacer()
        }
        .padding()
    }

    private var permissionDeniedView: some View {
        VStack(spacing: 16) {
            Spacer()
            Image(systemName: "photo.on.rectangle.angled")
                .font(.system(size: 56))
                .foregroundStyle(AppColor.accent.opacity(0.6))

            Text("사진 라이브러리 접근이 필요합니다")
                .font(AppFont.sectionTitle)
                .foregroundStyle(.white)

            Text("설정에서 접근을 허용해 주세요")
                .font(AppFont.caption)
                .foregroundStyle(.white.opacity(0.5))
                .multilineTextAlignment(.center)

            Button("설정 열기") {
                if let url = URL(string: UIApplication.openSettingsURLString) {
                    UIApplication.shared.open(url)
                }
            }
            .buttonStyle(PrimaryButtonStyle())
            .frame(width: 160)
            .padding(.top, 8)

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
            // Thumbnail with selection overlay
            ZStack(alignment: .topTrailing) {
                Group {
                    if let thumbnail {
                        Image(uiImage: thumbnail)
                            .resizable()
                            .aspectRatio(contentMode: .fill)
                    } else {
                        Rectangle()
                            .fill(AppColor.cardBackground)
                            .overlay {
                                Image(systemName: "video.fill")
                                    .foregroundStyle(.white.opacity(0.3))
                            }
                    }
                }
                .frame(width: 100, height: 75)
                .clipShape(RoundedRectangle(cornerRadius: 10))
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(isSelected ? AppColor.accent : Color.clear, lineWidth: 2)
                )
                .shadow(color: isSelected ? AppColor.accent.opacity(0.4) : .clear, radius: 6, x: 0, y: 0)

                // Checkmark overlay
                if isSelected {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 20))
                        .foregroundStyle(AppColor.accent)
                        .background(Circle().fill(.white).padding(2))
                        .offset(x: 4, y: -4)
                }
            }
            .scaleEffect(isSelected ? 1.0 : 0.95)
            .animation(.spring(response: 0.3, dampingFraction: 0.7), value: isSelected)

            // Info
            VStack(alignment: .leading, spacing: 5) {
                Text(video.gym.name)
                    .font(AppFont.cardTitle)
                    .foregroundStyle(.white)
                HStack(spacing: 8) {
                    Label(video.formattedDuration, systemImage: "clock")
                    Label(video.creationDate.formatted(date: .omitted, time: .shortened),
                          systemImage: "calendar")
                }
                .font(AppFont.caption)
                .foregroundStyle(.white.opacity(0.5))
            }

            Spacer()
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(isSelected ? AppColor.cardBackground : AppColor.cardBackground.opacity(0.5))
        )
        .task {
            await loadThumbnail()
        }
    }

    private func loadThumbnail() async {
        let manager = PHImageManager.default()
        let options = PHImageRequestOptions()
        options.isSynchronous = false
        options.deliveryMode = .highQualityFormat  // Single callback only
        options.resizeMode = .fast
        options.isNetworkAccessAllowed = true

        let size = CGSize(width: 200, height: 150)
        let result: UIImage? = await withCheckedContinuation { continuation in
            manager.requestImage(
                for: video.asset,
                targetSize: size,
                contentMode: .aspectFill,
                options: options
            ) { image, info in
                // highQualityFormat guarantees single callback
                continuation.resume(returning: image)
            }
        }
        await MainActor.run { thumbnail = result }
    }
}
