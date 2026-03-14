import Foundation
import Photos
import CoreLocation

struct DetectedVideo: Identifiable {
    let id: String
    let asset: PHAsset
    let gym: Gym
    let duration: TimeInterval
    let creationDate: Date

    var formattedDuration: String {
        let minutes = Int(duration) / 60
        let seconds = Int(duration) % 60
        return String(format: "%d:%02d", minutes, seconds)
    }
}

@MainActor
final class GalleryService: ObservableObject {
    @Published var detectedVideos: [DetectedVideo] = []
    @Published var isScanning = false
    @Published var authorizationStatus: PHAuthorizationStatus = .notDetermined
    @Published var errorMessage: String?

    private let gymDatabase: GymDatabase

    init(gymDatabase: GymDatabase = .shared) {
        self.gymDatabase = gymDatabase
    }

    func requestAuthorization() async {
        let status = await PHPhotoLibrary.requestAuthorization(for: .readWrite)
        authorizationStatus = status
    }

    func scanForClimbingVideos() async {
        guard authorizationStatus == .authorized || authorizationStatus == .limited else {
            errorMessage = "Photo library access required to scan for climbing videos."
            return
        }

        isScanning = true
        errorMessage = nil
        detectedVideos = []

        let calendar = Calendar.current
        let startOfDay = calendar.startOfDay(for: Date())
        guard let endOfDay = calendar.date(byAdding: .day, value: 1, to: startOfDay) else {
            isScanning = false
            return
        }

        let options = PHFetchOptions()
        options.predicate = NSPredicate(
            format: "mediaType == %d AND creationDate >= %@ AND creationDate < %@",
            PHAssetMediaType.video.rawValue,
            startOfDay as NSDate,
            endOfDay as NSDate
        )
        options.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: true)]

        let results = PHAsset.fetchAssets(with: options)
        var videos: [DetectedVideo] = []

        results.enumerateObjects { asset, _, _ in
            guard let location = asset.location else { return }
            guard let gym = self.gymDatabase.findNearestGym(location: location) else { return }

            let video = DetectedVideo(
                id: asset.localIdentifier,
                asset: asset,
                gym: gym,
                duration: asset.duration,
                creationDate: asset.creationDate ?? Date()
            )
            videos.append(video)
        }

        detectedVideos = videos
        isScanning = false
    }
}
