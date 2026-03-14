import SwiftUI

struct ResultView: View {
    @StateObject private var viewModel: ResultViewModel
    @State private var selectedClip: Clip?

    init(sessionId: String) {
        _viewModel = StateObject(wrappedValue: ResultViewModel(sessionId: sessionId))
    }

    private let columns = [
        GridItem(.flexible(), spacing: 8),
        GridItem(.flexible(), spacing: 8),
        GridItem(.flexible(), spacing: 8)
    ]

    var body: some View {
        VStack(spacing: 0) {
            filterBar
            clipGrid
        }
        .navigationTitle("Results")
        .navigationDestination(item: $selectedClip) { clip in
            ClipDetailView(clip: clip, sessionId: viewModel.sessionId)
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
                    Button("All") { viewModel.selectedDifficulty = nil; viewModel.applyFilters() }
                    ForEach(viewModel.availableDifficulties, id: \.self) { diff in
                        Button(diff) { viewModel.selectedDifficulty = diff; viewModel.applyFilters() }
                    }
                } label: {
                    filterChip(
                        title: viewModel.selectedDifficulty ?? "Difficulty",
                        isActive: viewModel.selectedDifficulty != nil
                    )
                }

                // Result filter
                Menu {
                    Button("All") { viewModel.selectedResult = nil; viewModel.applyFilters() }
                    Button("Success") { viewModel.selectedResult = "success"; viewModel.applyFilters() }
                    Button("Fail") { viewModel.selectedResult = "fail"; viewModel.applyFilters() }
                } label: {
                    filterChip(
                        title: viewModel.selectedResult?.capitalized ?? "Result",
                        isActive: viewModel.selectedResult != nil
                    )
                }

                // Me only toggle
                Button {
                    viewModel.showOnlyMe.toggle()
                    viewModel.applyFilters()
                } label: {
                    filterChip(title: "My Clips", isActive: viewModel.showOnlyMe)
                }

                if viewModel.selectedDifficulty != nil || viewModel.selectedResult != nil || viewModel.showOnlyMe {
                    Button {
                        viewModel.clearFilters()
                    } label: {
                        Text("Clear")
                            .font(.caption)
                            .foregroundStyle(.red)
                    }
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 8)
        }
        .background(Color(.systemGroupedBackground))
    }

    private func filterChip(title: String, isActive: Bool) -> some View {
        Text(title)
            .font(.subheadline)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(isActive ? Color.blue : Color(.secondarySystemFill))
            .foregroundStyle(isActive ? .white : .primary)
            .cornerRadius(16)
    }

    // MARK: - Clip Grid

    private var clipGrid: some View {
        Group {
            if viewModel.isLoading {
                ProgressView("Loading clips...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = viewModel.errorMessage {
                ContentUnavailableView("Error", systemImage: "exclamationmark.triangle", description: Text(error))
            } else if viewModel.filteredClips.isEmpty {
                ContentUnavailableView("No Clips", systemImage: "film.stack", description: Text("No clips match the current filters."))
            } else {
                ScrollView {
                    LazyVGrid(columns: columns, spacing: 8) {
                        ForEach(viewModel.filteredClips) { clip in
                            ClipCell(clip: clip)
                                .onTapGesture { selectedClip = clip }
                        }
                    }
                    .padding(8)
                }
            }
        }
    }
}

// MARK: - Clip Cell

private struct ClipCell: View {
    let clip: Clip

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            // Thumbnail
            if let urlString = clip.thumbnailUrl, let url = URL(string: urlString) {
                AsyncImage(url: url) { image in
                    image.resizable().aspectRatio(3/4, contentMode: .fill)
                } placeholder: {
                    Rectangle()
                        .fill(Color(.tertiarySystemFill))
                        .aspectRatio(3/4, contentMode: .fill)
                        .overlay(ProgressView())
                }
            } else {
                Rectangle()
                    .fill(Color(.tertiarySystemFill))
                    .aspectRatio(3/4, contentMode: .fill)
                    .overlay(
                        Image(systemName: "film")
                            .font(.title2)
                            .foregroundStyle(.secondary)
                    )
            }

            // Overlays
            VStack(alignment: .leading, spacing: 2) {
                // Result icon
                if let result = clip.result {
                    Image(systemName: result == "success" ? "checkmark.circle.fill" : "xmark.circle.fill")
                        .font(.caption)
                        .foregroundStyle(result == "success" ? .green : .red)
                        .padding(4)
                        .background(.ultraThinMaterial, in: Circle())
                }

                // Difficulty badge
                if let difficulty = clip.difficulty {
                    Text(difficulty)
                        .font(.caption2.bold())
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(.ultraThinMaterial)
                        .cornerRadius(4)
                }
            }
            .padding(4)
        }
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}
