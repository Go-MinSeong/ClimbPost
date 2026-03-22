import SwiftUI

private func fullURL(_ path: String?) -> URL? {
    guard let path else { return nil }
    if path.hasPrefix("http") { return URL(string: path) }
    return URL(string: Config.baseURLString + path)
}

struct CarouselView: View {
    let sessionId: String
    let initialClip: Clip?

    @StateObject private var viewModel: ResultViewModel
    @State private var selectedClipIds: [String] = []
    @State private var isSharing = false
    @State private var shareError: String?
    @State private var caption: String = ""
    @State private var isPublishing = false
    @State private var publishStatus: String?
    @State private var publishSuccess = false

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

            // 10-clip warning
            if selectedClips.count > 10 {
                HStack(spacing: 6) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.yellow)
                    Text("인스타그램 캐러셀은 최대 10개까지 가능합니다")
                        .font(AppFont.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(.horizontal)
                .padding(.vertical, 8)
                .background(Color.yellow.opacity(0.1))
            }

            // Caption input
            captionSection

            // Clip selection list
            clipSelectionList

            // Share buttons
            shareButtons
        }
        .background(AppColor.background)
        .navigationTitle("캐러셀 구성")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(AppColor.background, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .alert("공유 오류", isPresented: .init(
            get: { shareError != nil },
            set: { if !$0 { shareError = nil } }
        )) {
            Button("확인") { shareError = nil }
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
        VStack(alignment: .leading, spacing: 10) {
            Text("선택됨 (\(selectedClips.count)개)")
                .font(AppFont.cardTitle)
                .foregroundStyle(.primary)
                .padding(.horizontal)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    ForEach(Array(selectedClips.enumerated()), id: \.element.id) { index, clip in
                        selectedClipThumbnail(clip, order: index + 1)
                    }
                }
                .padding(.horizontal)
            }
        }
        .padding(.vertical, 14)
        .background(.ultraThinMaterial)
    }

    private func selectedClipThumbnail(_ clip: Clip, order: Int) -> some View {
        ZStack {
            // Thumbnail
            if let url = fullURL(clip.thumbnailUrl) {
                AsyncImage(url: url) { image in
                    image.resizable().aspectRatio(3.0/4.0, contentMode: .fill)
                } placeholder: {
                    AppColor.cardBackground
                }
                .frame(width: 80, height: 107)
                .clipShape(RoundedRectangle(cornerRadius: 8))
            } else {
                RoundedRectangle(cornerRadius: 8)
                    .fill(AppColor.cardBackground)
                    .frame(width: 80, height: 107)
                    .overlay(Image(systemName: "film").foregroundStyle(.secondary))
            }

            // Order number (top-left)
            VStack {
                HStack {
                    Text("\(order)")
                        .font(.system(size: 12, weight: .bold, design: .rounded))
                        .foregroundStyle(.white)
                        .frame(width: 22, height: 22)
                        .background(AppColor.accent, in: Circle())
                    Spacer()
                }
                Spacer()
            }
            .padding(4)

            // Remove button (top-right)
            VStack {
                HStack {
                    Spacer()
                    Button {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            selectedClipIds.removeAll { $0 == clip.id }
                        }
                    } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundStyle(.white)
                            .frame(width: 20, height: 20)
                            .background(.black.opacity(0.6), in: Circle())
                    }
                }
                Spacer()
            }
            .padding(4)

            // Drag handle hint (bottom center)
            VStack {
                Spacer()
                Image(systemName: "line.3.horizontal")
                    .font(.system(size: 10))
                    .foregroundStyle(.white.opacity(0.7))
                    .padding(.bottom, 4)
            }
        }
        .frame(width: 80, height: 107)
    }

    // MARK: - Clip Selection List

    private var clipSelectionList: some View {
        List {
            ForEach(viewModel.clips) { clip in
                clipRow(clip)
                    .contentShape(Rectangle())
                    .onTapGesture { toggleSelection(clip) }
                    .listRowBackground(
                        selectedClipIds.contains(clip.id)
                            ? AppColor.accent.opacity(0.08)
                            : Color.clear
                    )
            }
        }
        .listStyle(.plain)
    }

    private func clipRow(_ clip: Clip) -> some View {
        HStack(spacing: 12) {
            // Checkbox
            Image(systemName: selectedClipIds.contains(clip.id) ? "checkmark.circle.fill" : "circle")
                .foregroundStyle(selectedClipIds.contains(clip.id) ? AppColor.accent : .secondary)
                .font(.title3)

            // Thumbnail (larger)
            if let url = fullURL(clip.thumbnailUrl) {
                AsyncImage(url: url) { image in
                    image.resizable().aspectRatio(3.0/4.0, contentMode: .fill)
                } placeholder: {
                    AppColor.cardBackground
                }
                .frame(width: 56, height: 75)
                .clipShape(RoundedRectangle(cornerRadius: 6))
            } else {
                RoundedRectangle(cornerRadius: 6)
                    .fill(AppColor.cardBackground)
                    .frame(width: 56, height: 75)
                    .overlay(Image(systemName: "film").foregroundStyle(.secondary))
            }

            // Info
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 8) {
                    // Difficulty badge with color
                    if let difficulty = clip.difficulty {
                        Text(difficulty)
                            .font(.system(size: 12, weight: .bold, design: .rounded))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(AppColor.difficultyColor(difficulty).opacity(0.85))
                            .clipShape(RoundedRectangle(cornerRadius: 4))
                    }

                    // Success/fail icon
                    if let result = clip.result {
                        Image(systemName: result == "success" ? "checkmark.circle.fill" : "xmark.circle.fill")
                            .foregroundStyle(result == "success" ? AppColor.success : AppColor.fail)
                            .font(.system(size: 16))
                    }
                }

                // Duration
                if let start = clip.startTime, let end = clip.endTime {
                    let seconds = Int(end - start)
                    HStack(spacing: 4) {
                        Image(systemName: "clock")
                            .font(.system(size: 10))
                        Text(String(format: "%d:%02d", seconds / 60, seconds % 60))
                    }
                    .font(AppFont.caption)
                    .foregroundStyle(.secondary)
                }
            }

            Spacer()

            // Drag handle for selected items
            if selectedClipIds.contains(clip.id) {
                Image(systemName: "line.3.horizontal")
                    .foregroundStyle(.tertiary)
                    .font(.body)
            }
        }
    }

    // MARK: - Share Button

    // MARK: - Caption

    private var captionSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("캡션")
                .font(AppFont.caption)
                .foregroundStyle(.white.opacity(0.5))
            TextField("오늘의 클라이밍 🧗", text: $caption, axis: .vertical)
                .lineLimit(2...4)
                .padding(12)
                .background(AppColor.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: 10))
                .foregroundStyle(.white)
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
    }

    // MARK: - Share Buttons

    private var shareButtons: some View {
        VStack(spacing: 10) {
            // 직접 게시 (Instagram Graph API)
            Button {
                publishDirectly()
            } label: {
                HStack(spacing: 10) {
                    if isPublishing {
                        ProgressView().tint(.white)
                    } else {
                        Image(systemName: "paperplane.fill").font(.system(size: 16))
                    }
                    Text(publishStatus ?? (selectedClips.isEmpty ? "클립을 선택하세요" : "인스타그램에 직접 게시"))
                        .font(.system(size: 15, weight: .bold, design: .rounded))
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(
                    selectedClips.isEmpty || isPublishing
                        ? AnyShapeStyle(Color.gray.opacity(0.3))
                        : AnyShapeStyle(
                            LinearGradient(
                                colors: [
                                    Color(red: 0.51, green: 0.23, blue: 0.73),
                                    Color(red: 0.99, green: 0.36, blue: 0.22),
                                    Color(red: 0.96, green: 0.27, blue: 0.53)
                                ],
                                startPoint: .leading, endPoint: .trailing
                            )
                        )
                )
                .foregroundColor(.white)
                .clipShape(RoundedRectangle(cornerRadius: 14))
            }
            .disabled(selectedClips.isEmpty || isPublishing || isSharing)

            // 카메라롤 저장 (기존 방식)
            Button {
                shareToInstagram()
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: "square.and.arrow.down")
                    Text("카메라롤에 저장")
                        .font(.system(size: 14, weight: .medium, design: .rounded))
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
                .foregroundColor(.white.opacity(0.6))
            }
            .disabled(selectedClips.isEmpty || isSharing || isPublishing)

            // 게시 성공 메시지
            if publishSuccess {
                HStack {
                    Image(systemName: "checkmark.circle.fill").foregroundStyle(AppColor.success)
                    Text("인스타그램에 게시되었습니다!").font(AppFont.caption).foregroundStyle(AppColor.success)
                }
                .padding(.vertical, 4)
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 12)
    }

    // MARK: - Actions

    private func toggleSelection(_ clip: Clip) {
        withAnimation(.easeInOut(duration: 0.2)) {
            if let index = selectedClipIds.firstIndex(of: clip.id) {
                selectedClipIds.remove(at: index)
            } else {
                selectedClipIds.append(clip.id)
            }
        }
    }

    private func publishDirectly() {
        isPublishing = true
        publishStatus = "게시 요청 중..."
        publishSuccess = false

        Task {
            do {
                let response = try await APIClient.shared.publishToInstagram(
                    clipIds: selectedClipIds,
                    caption: caption.isEmpty ? nil : caption
                )
                let jobId = response.jobId
                publishStatus = "Instagram에 업로드 중..."

                // Poll until done
                for _ in 0..<120 {  // max 10 min
                    try await Task.sleep(nanoseconds: 5_000_000_000) // 5초
                    let status = try await APIClient.shared.getInstagramPublishStatus(jobId: jobId)

                    await MainActor.run {
                        switch status.status {
                        case "uploading": publishStatus = "영상 업로드 중..."
                        case "processing": publishStatus = "Instagram 처리 중..."
                        case "published":
                            publishStatus = nil
                            publishSuccess = true
                            isPublishing = false
                        case "failed":
                            publishStatus = nil
                            shareError = status.errorMessage ?? "게시 실패"
                            isPublishing = false
                        default: publishStatus = "처리 중..."
                        }
                    }

                    if status.status == "published" || status.status == "failed" { break }
                }
            } catch {
                await MainActor.run {
                    shareError = error.localizedDescription
                    publishStatus = nil
                    isPublishing = false
                }
            }
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
                let result = await ShareService.shared.shareToInstagram(videoURLs: videoURLs)
                await MainActor.run {
                    isSharing = false
                    if case .failure(let err) = result {
                        shareError = err.localizedDescription
                    }
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
