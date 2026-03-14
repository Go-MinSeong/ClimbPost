import Photos
import UIKit

final class ShareService {
    static let shared = ShareService()

    private let fileManager = FileManager.default

    private var tempDirectory: URL {
        fileManager.temporaryDirectory.appendingPathComponent("ClimbPostShare", isDirectory: true)
    }

    /// Downloads clip videos to temp directory using static file URLs (no auth needed).
    func prepareClipVideos(clips: [Clip], baseURLString: String) async throws -> [URL] {
        try? fileManager.removeItem(at: tempDirectory)
        try fileManager.createDirectory(at: tempDirectory, withIntermediateDirectories: true)

        var localURLs: [URL] = []

        for (index, clip) in clips.enumerated() {
            // Use static file URL (edited preferred, fallback to clip)
            let remotePath = clip.editedUrl ?? clip.clipUrl ?? "/clips/\(clip.id)/video"
            let urlString: String
            if remotePath.hasPrefix("http") {
                urlString = remotePath
            } else {
                urlString = "\(baseURLString)\(remotePath)"
            }
            guard let remoteURL = URL(string: urlString) else { continue }

            let (tempFileURL, _) = try await URLSession.shared.download(from: remoteURL)
            let destination = tempDirectory.appendingPathComponent("ClimbPost_\(index + 1).mp4")
            try? fileManager.removeItem(at: destination)
            try fileManager.moveItem(at: tempFileURL, to: destination)
            localURLs.append(destination)
        }

        return localURLs
    }

    /// Save clips to Camera Roll, then open Instagram for direct posting.
    @MainActor
    func shareToInstagram(videoURLs: [URL]) async -> Result<Void, Error> {
        // Step 1: Save all videos to Camera Roll
        do {
            for url in videoURLs {
                try await saveToCameraRoll(url: url)
            }
        } catch {
            return .failure(error)
        }

        // Step 2: Try to open Instagram
        // Option A: Instagram Stories (single video)
        // Option B: Open Instagram app (user creates carousel from camera roll)
        let instagramURL = URL(string: "instagram://app")!

        if UIApplication.shared.canOpenURL(instagramURL) {
            // Instagram is installed — open it
            // For Stories: instagram-stories://share
            if videoURLs.count == 1, let videoData = try? Data(contentsOf: videoURLs[0]) {
                // Single video → try Instagram Stories
                let storiesURL = URL(string: "instagram-stories://share?source_application=com.climbpost.app")!
                if UIApplication.shared.canOpenURL(storiesURL) {
                    let pasteboardItems: [[String: Any]] = [[
                        "com.instagram.sharedSticker.backgroundVideo": videoData
                    ]]
                    UIPasteboard.general.setItems(pasteboardItems, options: [
                        .expirationDate: Date().addingTimeInterval(300)
                    ])
                    await UIApplication.shared.open(storiesURL)
                    return .success(())
                }
            }

            // Multiple videos or Stories not available → open Instagram
            // User will create carousel from recently saved camera roll items
            await UIApplication.shared.open(instagramURL)
            return .success(())
        } else {
            // Instagram not installed → use system Share Sheet
            presentShareSheet(videoURLs: videoURLs)
            return .success(())
        }
    }

    /// Presents a UIActivityViewController (Share Sheet) with the given video files.
    @MainActor
    func presentShareSheet(videoURLs: [URL]) {
        guard !videoURLs.isEmpty else { return }

        let activityVC = UIActivityViewController(
            activityItems: videoURLs,
            applicationActivities: nil
        )
        activityVC.excludedActivityTypes = [.addToReadingList, .assignToContact, .print]

        guard let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
              let rootVC = windowScene.windows.first?.rootViewController else {
            return
        }

        var topVC = rootVC
        while let presented = topVC.presentedViewController {
            topVC = presented
        }

        if let popover = activityVC.popoverPresentationController {
            popover.sourceView = topVC.view
            popover.sourceRect = CGRect(x: topVC.view.bounds.midX, y: topVC.view.bounds.maxY - 50, width: 0, height: 0)
        }

        topVC.present(activityVC, animated: true)
    }

    /// Save a single video to Camera Roll.
    private func saveToCameraRoll(url: URL) async throws {
        try await PHPhotoLibrary.shared().performChanges {
            PHAssetChangeRequest.creationRequestForAssetFromVideo(atFileURL: url)
        }
    }

    func cleanUp() {
        try? fileManager.removeItem(at: tempDirectory)
    }
}
