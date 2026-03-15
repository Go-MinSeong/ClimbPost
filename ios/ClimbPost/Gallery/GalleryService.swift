import Foundation
import Photos
import CoreLocation
import os.log

private let logger = Logger(subsystem: "com.climbpost", category: "Gallery")

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
        #if targetEnvironment(simulator)
        authorizationStatus = .authorized
        #else
        let status = await PHPhotoLibrary.requestAuthorization(for: .readWrite)
        authorizationStatus = status
        logger.info("Photo auth: \(String(describing: status.rawValue))")
        #endif
    }

    func scanForClimbingVideos() async {
        #if !targetEnvironment(simulator)
        guard authorizationStatus == .authorized || authorizationStatus == .limited else {
            errorMessage = "사진 라이브러리 접근 권한이 필요합니다."
            return
        }
        #endif

        isScanning = true
        errorMessage = nil

        let gymDB = gymDatabase

        let videos: [DetectedVideo] = await Task.detached(priority: .userInitiated) {
            logger.info("Scan started")

            let options = PHFetchOptions()
            // Only fetch videos with location data — skip locationless ones entirely
            #if targetEnvironment(simulator)
            options.predicate = NSPredicate(
                format: "mediaType == %d",
                PHAssetMediaType.video.rawValue
            )
            #else
            let calendar = Calendar.current
            guard let fiveDaysAgo = calendar.date(byAdding: .day, value: -5, to: Date()) else {
                return []
            }
            options.predicate = NSPredicate(
                format: "mediaType == %d AND creationDate >= %@",
                PHAssetMediaType.video.rawValue,
                fiveDaysAgo as NSDate
            )
            #endif
            options.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
            options.fetchLimit = 200 // Safety limit

            let results = PHAsset.fetchAssets(with: options)
            logger.info("Found \(results.count) videos in last 5 days")

            var found: [DetectedVideo] = []
            let fallbackGym = gymDB.gyms.first

            for i in 0..<results.count {
                let asset = results.object(at: i)

                let gym: Gym?
                #if targetEnvironment(simulator)
                gym = asset.location.flatMap { gymDB.findNearestGym(location: $0) } ?? fallbackGym
                #else
                // Skip videos without location — they can't be matched to a gym
                guard let location = asset.location else { continue }
                gym = gymDB.findNearestGym(location: location)
                #endif

                guard let gym else { continue }

                found.append(DetectedVideo(
                    id: asset.localIdentifier,
                    asset: asset,
                    gym: gym,
                    duration: asset.duration,
                    creationDate: asset.creationDate ?? Date()
                ))
            }

            logger.info("Matched \(found.count) climbing videos")
            return found
        }.value

        detectedVideos = videos
        isScanning = false
    }
}
