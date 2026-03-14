import AVFoundation
import Foundation
import Photos

final class UploadService: NSObject {
    static let shared = UploadService()

    private var backgroundSession: URLSession!
    private var uploadState: UploadState?
    private var activeTaskProgress: [Int: String] = [:] // taskIdentifier -> videoId

    override init() {
        super.init()
        let config = URLSessionConfiguration.background(withIdentifier: "com.climbpost.upload")
        config.isDiscretionary = false
        config.sessionSendsLaunchEvents = true
        backgroundSession = URLSession(configuration: config, delegate: self, delegateQueue: nil)
    }

    /// Run the full upload flow: create session -> upload each video -> start analysis
    func uploadVideos(_ videos: [DetectedVideo], state: UploadState) async {
        guard let firstVideo = videos.first else { return }

        await MainActor.run {
            self.uploadState = state
            state.isUploading = true
            state.totalFiles = videos.count
            state.errorMessage = nil
        }

        let apiClient = APIClient.shared
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd"
        let recordedDate = dateFormatter.string(from: firstVideo.creationDate)

        do {
            // Step 1: Create session
            NSLog("[Upload] Step 1: Creating session for gym \(firstVideo.gym.id)")
            let sessionResponse = try await apiClient.createSession(
                gymId: firstVideo.gym.id,
                recordedDate: recordedDate
            )

            let sessionId = sessionResponse.id
            NSLog("[Upload] Session created: \(sessionId)")
            await MainActor.run { state.sessionId = sessionId }

            // Step 2: Upload each video
            for (index, video) in videos.enumerated() {
                await MainActor.run {
                    state.currentFileIndex = index + 1
                    state.currentFile = video.gym.name
                }

                NSLog("[Upload] Step 2.\(index+1): Exporting video \(index+1)/\(videos.count)")
                let fileURL = try await exportVideoToTemp(asset: video.asset)
                let fileSize = (try? FileManager.default.attributesOfItem(atPath: fileURL.path)[.size] as? Int) ?? 0
                NSLog("[Upload] Exported to \(fileURL.lastPathComponent) (\(fileSize / 1_000_000)MB)")
                defer { try? FileManager.default.removeItem(at: fileURL) }

                NSLog("[Upload] Uploading \(fileURL.lastPathComponent)...")
                _ = try await apiClient.uploadVideo(
                    sessionId: sessionId,
                    fileURL: fileURL
                ) { fraction in
                    Task { @MainActor in
                        state.fileProgress[video.id] = fraction
                        let completedPortion = Double(index) / Double(videos.count)
                        let currentPortion = fraction / Double(videos.count)
                        state.progress = completedPortion + currentPortion
                    }
                }
                NSLog("[Upload] Video \(index+1) uploaded successfully")

                await MainActor.run {
                    state.fileProgress[video.id] = 1.0
                }
            }

            // Step 3: Start analysis
            NSLog("[Upload] Step 3: Starting analysis")
            let analysisResponse = try await apiClient.startAnalysis(sessionId: sessionId)
            NSLog("[Upload] Analysis started: job \(analysisResponse.id)")

            await MainActor.run {
                state.progress = 1.0
                state.isComplete = true
                state.isUploading = false
                state.jobId = analysisResponse.id
            }

        } catch {
            NSLog("[Upload] ❌ ERROR: \(error)")
            await MainActor.run {
                state.errorMessage = error.localizedDescription
                state.isUploading = false
            }
        }
    }

    /// Export a PHAsset video to a temporary file URL
    private func exportVideoToTemp(asset: PHAsset) async throws -> URL {
        try await withCheckedThrowingContinuation { continuation in
            let options = PHVideoRequestOptions()
            options.version = .current
            options.deliveryMode = .highQualityFormat
            options.isNetworkAccessAllowed = true

            PHImageManager.default().requestAVAsset(
                forVideo: asset,
                options: options
            ) { avAsset, _, info in
                guard let urlAsset = avAsset as? AVURLAsset else {
                    // If we can't get a URL asset, export via PHAssetResourceManager
                    self.exportViaResourceManager(asset: asset, continuation: continuation)
                    return
                }

                let tempDir = FileManager.default.temporaryDirectory
                let fileName = "\(UUID().uuidString).mp4"
                let destURL = tempDir.appendingPathComponent(fileName)

                do {
                    try FileManager.default.copyItem(at: urlAsset.url, to: destURL)
                    continuation.resume(returning: destURL)
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    private func exportViaResourceManager(
        asset: PHAsset,
        continuation: CheckedContinuation<URL, Error>
    ) {
        let resources = PHAssetResource.assetResources(for: asset)
        guard let videoResource = resources.first(where: { $0.type == .video }) else {
            continuation.resume(throwing: UploadError.noVideoResource)
            return
        }

        let tempDir = FileManager.default.temporaryDirectory
        let fileName = "\(UUID().uuidString).mp4"
        let destURL = tempDir.appendingPathComponent(fileName)

        let options = PHAssetResourceRequestOptions()
        options.isNetworkAccessAllowed = true

        PHAssetResourceManager.default().writeData(
            for: videoResource,
            toFile: destURL,
            options: options
        ) { error in
            if let error {
                continuation.resume(throwing: error)
            } else {
                continuation.resume(returning: destURL)
            }
        }
    }
}

// MARK: - URLSessionDelegate (background upload support)

extension UploadService: URLSessionDelegate, URLSessionTaskDelegate {
    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        didSendBodyData bytesSent: Int64,
        totalBytesSent: Int64,
        totalBytesExpectedToSend: Int64
    ) {
        guard totalBytesExpectedToSend > 0 else { return }
        let fraction = Double(totalBytesSent) / Double(totalBytesExpectedToSend)

        if let videoId = activeTaskProgress[task.taskIdentifier] {
            Task { @MainActor in
                self.uploadState?.fileProgress[videoId] = fraction
            }
        }
    }

    func urlSessionDidFinishEvents(forBackgroundURLSession session: URLSession) {
        // Called when background session events are done
    }
}

// MARK: - Errors

enum UploadError: LocalizedError {
    case noVideoResource
    case exportFailed

    var errorDescription: String? {
        switch self {
        case .noVideoResource:
            return "Could not find video data for this asset"
        case .exportFailed:
            return "Failed to export video file"
        }
    }
}
