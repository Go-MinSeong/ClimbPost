import UIKit

final class ShareService {
    static let shared = ShareService()

    private let fileManager = FileManager.default

    private var tempDirectory: URL {
        fileManager.temporaryDirectory.appendingPathComponent("ClimbPostShare", isDirectory: true)
    }

    /// Downloads clip videos to a temp directory and returns their local file URLs.
    func prepareClipVideos(clips: [Clip], baseURLString: String) async throws -> [URL] {
        // Clean up previous temp files
        try? fileManager.removeItem(at: tempDirectory)
        try fileManager.createDirectory(at: tempDirectory, withIntermediateDirectories: true)

        var localURLs: [URL] = []

        for (index, clip) in clips.enumerated() {
            let urlString = "\(baseURLString)/clips/\(clip.id)/video"
            guard let remoteURL = URL(string: urlString) else { continue }

            var request = URLRequest(url: remoteURL)
            if let token = KeychainHelper.load(.accessToken) {
                request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            }

            let (tempFileURL, _) = try await URLSession.shared.download(for: request)
            let destination = tempDirectory.appendingPathComponent("clip_\(index + 1).mp4")
            try? fileManager.removeItem(at: destination)
            try fileManager.moveItem(at: tempFileURL, to: destination)
            localURLs.append(destination)
        }

        return localURLs
    }

    /// Presents a UIActivityViewController (Share Sheet) with the given video files.
    @MainActor
    func presentShareSheet(videoURLs: [URL]) {
        guard !videoURLs.isEmpty else { return }

        let activityVC = UIActivityViewController(
            activityItems: videoURLs,
            applicationActivities: nil
        )

        // Exclude irrelevant activity types
        activityVC.excludedActivityTypes = [
            .addToReadingList,
            .assignToContact,
            .print
        ]

        guard let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
              let rootVC = windowScene.windows.first?.rootViewController else {
            return
        }

        // Find the topmost presented view controller
        var topVC = rootVC
        while let presented = topVC.presentedViewController {
            topVC = presented
        }

        // iPad popover support
        if let popover = activityVC.popoverPresentationController {
            popover.sourceView = topVC.view
            popover.sourceRect = CGRect(x: topVC.view.bounds.midX, y: topVC.view.bounds.maxY - 50, width: 0, height: 0)
        }

        topVC.present(activityVC, animated: true)
    }

    /// Clean up temp files when done.
    func cleanUp() {
        try? fileManager.removeItem(at: tempDirectory)
    }
}
