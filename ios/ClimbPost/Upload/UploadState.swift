import Foundation

@MainActor
final class UploadState: ObservableObject {
    @Published var isUploading = false
    @Published var progress: Double = 0
    @Published var currentFile: String?
    @Published var currentFileIndex: Int = 0
    @Published var totalFiles: Int = 0
    @Published var isComplete = false
    @Published var errorMessage: String?
    @Published var sessionId: String?
    @Published var jobId: String?

    /// Per-file progress values (keyed by video local identifier)
    @Published var fileProgress: [String: Double] = [:]

    func reset() {
        isUploading = false
        progress = 0
        currentFile = nil
        currentFileIndex = 0
        totalFiles = 0
        isComplete = false
        errorMessage = nil
        sessionId = nil
        jobId = nil
        fileProgress = [:]
    }
}
