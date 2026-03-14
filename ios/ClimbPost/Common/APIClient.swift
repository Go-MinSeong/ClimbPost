import Foundation

// MARK: - Protocol

protocol APIClientProtocol {
    func login(provider: String, idToken: String) async throws -> AuthResponse
    func refreshToken() async throws -> AuthResponse
    func getMe() async throws -> UserProfile
    func createSession(gymId: String, recordedDate: String) async throws -> CreateSessionResponse
    func uploadVideo(sessionId: String, fileURL: URL, progress: @escaping (Double) -> Void) async throws -> UploadResponse
    func startAnalysis(sessionId: String) async throws -> StartAnalysisResponse
    func getAnalysisStatus(sessionId: String) async throws -> AnalysisStatus
    func getAllClips() async throws -> [Clip]
    func getClips(sessionId: String, filters: ClipFilter?) async throws -> [Clip]
    func registerPushToken(_ token: String) async throws
}

// MARK: - Errors

enum APIError: LocalizedError {
    case invalidURL
    case unauthorized
    case serverError(statusCode: Int, message: String?)
    case decodingError(Error)
    case networkError(Error)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL"
        case .unauthorized:
            return "Unauthorized — please sign in again"
        case .serverError(let code, let message):
            return "Server error (\(code)): \(message ?? "Unknown")"
        case .decodingError(let error):
            return "Failed to parse response: \(error.localizedDescription)"
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        }
    }
}

// MARK: - Implementation

final class APIClient: APIClientProtocol {
    static let shared = APIClient()

    private let session: URLSession
    private let baseURL: URL
    private let decoder: JSONDecoder

    init(baseURL: URL = Config.baseURL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
        self.decoder = JSONDecoder()
    }

    // MARK: - Auth

    func login(provider: String, idToken: String) async throws -> AuthResponse {
        let body: [String: String] = ["provider": provider, "id_token": idToken]
        return try await post("/auth/login", body: body)
    }

    func refreshToken() async throws -> AuthResponse {
        return try await post("/auth/refresh", body: Optional<String>.none, authenticated: true)
    }

    func getMe() async throws -> UserProfile {
        return try await get("/auth/me", authenticated: true)
    }

    // MARK: - Sessions

    func createSession(gymId: String, recordedDate: String) async throws -> CreateSessionResponse {
        let body = CreateSessionRequest(gymId: gymId, recordedDate: recordedDate)
        return try await post("/videos/sessions", body: body, authenticated: true)
    }

    func startAnalysis(sessionId: String) async throws -> StartAnalysisResponse {
        return try await post("/videos/sessions/\(sessionId)/start-analysis", body: Optional<String>.none, authenticated: true)
    }

    // MARK: - Upload

    func uploadVideo(sessionId: String, fileURL: URL, progress: @escaping (Double) -> Void) async throws -> UploadResponse {
        let url = baseURL.appendingPathComponent("/videos/upload/\(sessionId)")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        try addAuthHeader(to: &request)

        let boundary = UUID().uuidString
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        let fileData = try Data(contentsOf: fileURL)
        var body = Data()
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(fileURL.lastPathComponent)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: video/mp4\r\n\r\n".data(using: .utf8)!)
        body.append(fileData)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)

        request.httpBody = body

        let (data, response) = try await session.data(for: request)
        try validateResponse(response)
        return try decoder.decode(UploadResponse.self, from: data)
    }

    // MARK: - Analysis

    func getAnalysisStatus(sessionId: String) async throws -> AnalysisStatus {
        return try await get("/analysis/\(sessionId)/status", authenticated: true)
    }

    // MARK: - Clips

    func getAllClips() async throws -> [Clip] {
        return try await get("/clips", authenticated: true)
    }

    func getClips(sessionId: String, filters: ClipFilter?) async throws -> [Clip] {
        var queryItems = [URLQueryItem(name: "session_id", value: sessionId)]
        if let difficulty = filters?.difficulty {
            queryItems.append(URLQueryItem(name: "difficulty", value: difficulty))
        }
        if let result = filters?.result {
            queryItems.append(URLQueryItem(name: "result", value: result))
        }
        if let isMe = filters?.isMe {
            queryItems.append(URLQueryItem(name: "is_me", value: isMe ? "true" : "false"))
        }

        return try await get("/clips", queryItems: queryItems, authenticated: true)
    }

    // MARK: - Push

    func registerPushToken(_ token: String) async throws {
        let body = RegisterPushRequest(deviceToken: token)
        let _: [String: Bool] = try await post("/push/register", body: body, authenticated: true)
    }

    // MARK: - Helpers

    private func get<T: Decodable>(
        _ path: String,
        queryItems: [URLQueryItem]? = nil,
        authenticated: Bool = false
    ) async throws -> T {
        var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        if let queryItems, !queryItems.isEmpty {
            components.queryItems = queryItems
        }
        guard let url = components.url else { throw APIError.invalidURL }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        if authenticated { try addAuthHeader(to: &request) }

        let (data, response) = try await session.data(for: request)
        try validateResponse(response)
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(error)
        }
    }

    private func post<T: Decodable, B: Encodable>(
        _ path: String,
        body: B?,
        authenticated: Bool = false
    ) async throws -> T {
        let url = baseURL.appendingPathComponent(path)
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if authenticated { try addAuthHeader(to: &request) }

        if let body {
            request.httpBody = try JSONEncoder().encode(body)
        }

        let (data, response) = try await session.data(for: request)
        try validateResponse(response)
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(error)
        }
    }

    private func addAuthHeader(to request: inout URLRequest) throws {
        guard let token = KeychainHelper.load(.accessToken) else {
            throw APIError.unauthorized
        }
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    }

    private func validateResponse(_ response: URLResponse) throws {
        guard let httpResponse = response as? HTTPURLResponse else { return }
        switch httpResponse.statusCode {
        case 200...299:
            return
        case 401:
            throw APIError.unauthorized
        default:
            throw APIError.serverError(statusCode: httpResponse.statusCode, message: nil)
        }
    }
}
