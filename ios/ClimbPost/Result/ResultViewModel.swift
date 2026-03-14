import Foundation
import Combine

@MainActor
final class ResultViewModel: ObservableObject {
    @Published var clips: [Clip] = []
    @Published var filteredClips: [Clip] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    // Filters
    @Published var selectedDifficulty: String?
    @Published var selectedResult: String?
    @Published var showOnlyMe = false

    let sessionId: String
    private let apiClient: APIClientProtocol

    var availableDifficulties: [String] {
        Array(Set(clips.compactMap { $0.difficulty })).sorted()
    }

    init(sessionId: String, apiClient: APIClientProtocol = APIClient.shared) {
        self.sessionId = sessionId
        self.apiClient = apiClient
    }

    func fetchClips() async {
        isLoading = true
        errorMessage = nil
        do {
            clips = try await apiClient.getClips(sessionId: sessionId, filters: nil)
            applyFilters()
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    func applyFilters() {
        var result = clips

        if let difficulty = selectedDifficulty {
            result = result.filter { $0.difficulty == difficulty }
        }
        if let resultFilter = selectedResult {
            result = result.filter { $0.result == resultFilter }
        }
        if showOnlyMe {
            result = result.filter { $0.isMe == true }
        }

        filteredClips = result
    }

    func clearFilters() {
        selectedDifficulty = nil
        selectedResult = nil
        showOnlyMe = false
        applyFilters()
    }
}
