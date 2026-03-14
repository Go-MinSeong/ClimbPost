import Foundation

enum Config {
    // PHASE 1: home network — backend runs on same machine
    static let baseURL: URL = {
        guard let url = URL(string: baseURLString) else {
            fatalError("Invalid base URL: \(baseURLString)")
        }
        return url
    }()

    #if DEBUG
    static let baseURLString = "http://localhost:8000"
    #else
    static let baseURLString = "http://localhost:8000"
    #endif
}
