import SwiftUI

private func fullURL(_ path: String?) -> URL? {
    guard let path else { return nil }
    if path.hasPrefix("http") { return URL(string: path) }
    return URL(string: Config.baseURLString + path)
}

struct ResultView: View {
    @StateObject private var viewModel: ResultViewModel
    @State private var selectedClip: Clip?
    @State private var showCarousel = false

    init(sessionId: String) {
        _viewModel = StateObject(wrappedValue: ResultViewModel(sessionId: sessionId))
    }

    private let columns = [
        GridItem(.flexible(), spacing: 8),
        GridItem(.flexible(), spacing: 8),
        GridItem(.flexible(), spacing: 8)
    ]

    private var successCount: Int {
        viewModel.filteredClips.filter { $0.result == "success" }.count
    }

    private var failCount: Int {
        viewModel.filteredClips.filter { $0.result == "fail" }.count
    }

    private var hasActiveFilters: Bool {
        viewModel.selectedDifficulty != nil || viewModel.selectedResult != nil || viewModel.showOnlyMe
    }

    var body: some View {
        VStack(spacing: 0) {
            filterBar
            clipGrid
        }
        .background(AppColor.background)
        .navigationTitle("분석 결과")
        .overlay(alignment: .bottom) {
            if !viewModel.filteredClips.isEmpty {
                Button {
                    showCarousel = true
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: "square.and.arrow.up")
                        Text("공유할 클립 선택")
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
                .shadow(color: AppColor.accent.opacity(0.4), radius: 12, y: 4)
                .padding(.horizontal, 20)
                .padding(.bottom, 16)
            }
        }
        .navigationDestination(item: $selectedClip) { clip in
            ClipDetailView(clip: clip, sessionId: viewModel.sessionId)
        }
        .navigationDestination(isPresented: $showCarousel) {
            CarouselView(sessionId: viewModel.sessionId)
        }
        .task {
            await viewModel.fetchClips()
        }
    }

    // MARK: - Filter Bar

    private var filterBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                // Difficulty filter
                Menu {
                    Button("전체") { viewModel.selectedDifficulty = nil; viewModel.applyFilters() }
                    ForEach(viewModel.availableDifficulties, id: \.self) { diff in
                        Button {
                            viewModel.selectedDifficulty = diff
                            viewModel.applyFilters()
                        } label: {
                            Label(diff, systemImage: "circle.fill")
                        }
                    }
                } label: {
                    filterChip(
                        title: viewModel.selectedDifficulty ?? "난이도",
                        icon: "circle.fill",
                        isActive: viewModel.selectedDifficulty != nil,
                        accentColor: viewModel.selectedDifficulty != nil
                            ? AppColor.difficultyColor(viewModel.selectedDifficulty)
                            : nil
                    )
                }

                // Result filter
                Menu {
                    Button("전체") { viewModel.selectedResult = nil; viewModel.applyFilters() }
                    Button {
                        viewModel.selectedResult = "success"
                        viewModel.applyFilters()
                    } label: {
                        Label("완등", systemImage: "checkmark")
                    }
                    Button {
                        viewModel.selectedResult = "fail"
                        viewModel.applyFilters()
                    } label: {
                        Label("실패", systemImage: "xmark")
                    }
                } label: {
                    filterChip(
                        title: viewModel.selectedResult == "success" ? "완등" :
                               viewModel.selectedResult == "fail" ? "실패" : "결과",
                        icon: viewModel.selectedResult == "success" ? "checkmark" :
                              viewModel.selectedResult == "fail" ? "xmark" : "flag",
                        isActive: viewModel.selectedResult != nil
                    )
                }

                // Me only toggle
                Button {
                    viewModel.showOnlyMe.toggle()
                    viewModel.applyFilters()
                } label: {
                    filterChip(
                        title: "내 클립만",
                        icon: "person.fill",
                        isActive: viewModel.showOnlyMe
                    )
                }

                // Clear button
                if hasActiveFilters {
                    Button {
                        viewModel.clearFilters()
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "xmark.circle.fill")
                            Text("초기화")
                        }
                        .font(AppFont.caption)
                        .foregroundStyle(AppColor.fail)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(AppColor.fail.opacity(0.15))
                        .clipShape(Capsule())
                    }
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 10)
        }
        .background(.ultraThinMaterial)
    }

    private func filterChip(title: String, icon: String, isActive: Bool, accentColor: Color? = nil) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .font(.system(size: 10))
                .foregroundStyle(accentColor ?? (isActive ? .white : .secondary))
            Text(title)
        }
        .font(AppFont.badge)
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(isActive ? AppColor.accent : AppColor.cardBackground)
        .foregroundStyle(isActive ? .white : .primary)
        .clipShape(Capsule())
    }

    // MARK: - Stats Header

    private var statsHeader: some View {
        HStack(spacing: 16) {
            statItem(label: "총", value: "\(viewModel.filteredClips.count)개 클립")
            Divider().frame(height: 16)
            statItem(label: "완등", value: "\(successCount)", color: AppColor.success)
            Divider().frame(height: 16)
            statItem(label: "실패", value: "\(failCount)", color: AppColor.fail)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
    }

    private func statItem(label: String, value: String, color: Color = AppColor.accent) -> some View {
        HStack(spacing: 4) {
            Text(label)
                .font(AppFont.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(AppFont.badge)
                .foregroundStyle(color)
        }
    }

    // MARK: - Clip Grid

    private var clipGrid: some View {
        Group {
            if viewModel.isLoading {
                VStack(spacing: 12) {
                    ProgressView()
                        .tint(AppColor.accent)
                    Text("클립을 불러오는 중...")
                        .font(AppFont.caption)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = viewModel.errorMessage {
                ContentUnavailableView {
                    Label("오류", systemImage: "exclamationmark.triangle")
                } description: {
                    Text(error)
                }
            } else if viewModel.filteredClips.isEmpty {
                ContentUnavailableView {
                    Label("클립 없음", systemImage: "film.stack")
                } description: {
                    Text("필터에 맞는 클립이 없습니다")
                }
            } else {
                ScrollView {
                    statsHeader

                    LazyVGrid(columns: columns, spacing: 8) {
                        ForEach(viewModel.filteredClips) { clip in
                            ClipCell(clip: clip)
                                .onTapGesture { selectedClip = clip }
                        }
                    }
                    .padding(.horizontal, 8)
                    .padding(.bottom, 8)
                }
            }
        }
    }
}

// MARK: - Clip Cell

private struct ClipCell: View {
    let clip: Clip
    @State private var isPressed = false

    private var duration: String {
        guard let start = clip.startTime, let end = clip.endTime else { return "" }
        let seconds = Int(end - start)
        return String(format: "%d:%02d", seconds / 60, seconds % 60)
    }

    var body: some View {
        ZStack {
            // Thumbnail
            thumbnailImage
                .aspectRatio(3.0/4.0, contentMode: .fill)
                .clipped()

            // Bottom gradient overlay
            VStack {
                Spacer()
                LinearGradient(
                    colors: [.black.opacity(0.7), .clear],
                    startPoint: .bottom,
                    endPoint: .top
                )
                .frame(height: 60)
            }

            // Top-right: success/fail icon
            VStack {
                HStack {
                    Spacer()
                    if let result = clip.result {
                        Image(systemName: result == "success" ? "checkmark.circle.fill" : "xmark.circle.fill")
                            .font(.system(size: 16, weight: .bold))
                            .foregroundStyle(result == "success" ? AppColor.success : AppColor.fail)
                            .padding(6)
                            .background(.ultraThinMaterial, in: Circle())
                    }
                }
                Spacer()
            }
            .padding(6)

            // Top-left: "나" badge if is_me
            VStack {
                HStack {
                    if clip.isMe == true {
                        HStack(spacing: 2) {
                            Image(systemName: "person.fill")
                                .font(.system(size: 8))
                            Text("나")
                                .font(.system(size: 10, weight: .bold))
                        }
                        .foregroundStyle(.white)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 3)
                        .background(Color.blue, in: Capsule())
                    }
                    Spacer()
                }
                Spacer()
            }
            .padding(6)

            // Bottom-left overlay: difficulty + duration
            VStack {
                Spacer()
                HStack {
                    VStack(alignment: .leading, spacing: 3) {
                        if let difficulty = clip.difficulty {
                            Text(difficulty)
                                .font(.system(size: 11, weight: .bold, design: .rounded))
                                .foregroundStyle(.white)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(AppColor.difficultyColor(difficulty).opacity(0.85))
                                .clipShape(RoundedRectangle(cornerRadius: 4))
                        }
                        if !duration.isEmpty {
                            Text(duration)
                                .font(.system(size: 10, weight: .medium, design: .monospaced))
                                .foregroundStyle(.white.opacity(0.9))
                        }
                    }
                    Spacer()
                }
            }
            .padding(6)
        }
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .shadow(color: .black.opacity(0.2), radius: 4, y: 2)
        .scaleEffect(isPressed ? 0.95 : 1.0)
        .animation(.easeInOut(duration: 0.15), value: isPressed)
        .onLongPressGesture(minimumDuration: .infinity, pressing: { pressing in
            isPressed = pressing
        }, perform: {})
    }

    @ViewBuilder
    private var thumbnailImage: some View {
        if let url = fullURL(clip.thumbnailUrl) {
            AsyncImage(url: url) { image in
                image.resizable()
            } placeholder: {
                Rectangle()
                    .fill(AppColor.cardBackground)
                    .overlay(ProgressView().tint(AppColor.accent))
            }
        } else {
            Rectangle()
                .fill(AppColor.cardBackground)
                .overlay(
                    Image(systemName: "film")
                        .font(.title2)
                        .foregroundStyle(.secondary)
                )
        }
    }
}
