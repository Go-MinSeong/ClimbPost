import Foundation

enum Config {
    // PHASE 1: home network — backend runs on same machine
    static let baseURL: URL = {
        guard let url = URL(string: baseURLString) else {
            fatalError("Invalid base URL: \(baseURLString)")
        }
        return url
    }()

    #if targetEnvironment(simulator)
    static let baseURLString = "http://localhost:8000"
    #elseif DEBUG
    static let baseURLString = "http://100.71.197.112:8000"  // Tailscale VPN → GPU server
    #else
    static let baseURLString = "https://your-server.com"
    #endif
}
