import Foundation
import CoreLocation

struct Gym: Codable, Identifiable {
    let id: String
    let name: String
    let latitude: Double
    let longitude: Double
    let colorMapFile: String?

    enum CodingKeys: String, CodingKey {
        case id, name, latitude, longitude
        case colorMapFile = "color_map_file"
    }

    var location: CLLocation {
        CLLocation(latitude: latitude, longitude: longitude)
    }
}

final class GymDatabase {
    static let shared = GymDatabase()

    private(set) var gyms: [Gym] = []

    /// Maximum distance in meters to consider a video as recorded at a gym
    private let matchRadius: CLLocationDistance = 500

    init() {
        loadGyms()
    }

    private func loadGyms() {
        guard let url = Bundle.main.url(forResource: "gyms", withExtension: "json", subdirectory: "Resources") ?? Bundle.main.url(forResource: "gyms", withExtension: "json") else {
            print("[GymDatabase] gyms.json not found in bundle")
            return
        }
        do {
            let data = try Data(contentsOf: url)
            let container = try JSONDecoder().decode(GymContainer.self, from: data)
            gyms = container.gyms
        } catch {
            print("[GymDatabase] Failed to decode gyms.json: \(error)")
        }
    }

    /// Find the nearest gym within 500m of the given location
    func findNearestGym(location: CLLocation) -> Gym? {
        var bestGym: Gym?
        var bestDistance: CLLocationDistance = .greatestFiniteMagnitude

        for gym in gyms {
            let distance = location.distance(from: gym.location)
            if distance <= matchRadius && distance < bestDistance {
                bestDistance = distance
                bestGym = gym
            }
        }

        return bestGym
    }
}

private struct GymContainer: Codable {
    let gyms: [Gym]
}
