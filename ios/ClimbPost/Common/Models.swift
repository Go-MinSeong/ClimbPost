import Foundation

// MARK: - Auth

struct AuthResponse: Codable {
    let accessToken: String
    let tokenType: String
    let userId: String

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case tokenType = "token_type"
        case userId = "user_id"
    }
}

struct UserProfile: Codable {
    let userId: String
    let email: String?
    let provider: String

    enum CodingKeys: String, CodingKey {
        case userId = "user_id"
        case email
        case provider
    }
}

// MARK: - Video Sessions

struct CreateSessionRequest: Codable {
    let gymId: String
    let recordedDate: String

    enum CodingKeys: String, CodingKey {
        case gymId = "gym_id"
        case recordedDate = "recorded_date"
    }
}

struct CreateSessionResponse: Codable {
    let sessionId: String

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
    }
}

struct UploadResponse: Codable {
    let rawVideoId: String
    let fileUrl: String

    enum CodingKeys: String, CodingKey {
        case rawVideoId = "raw_video_id"
        case fileUrl = "file_url"
    }
}

struct StartAnalysisResponse: Codable {
    let jobId: String

    enum CodingKeys: String, CodingKey {
        case jobId = "job_id"
    }
}

// MARK: - Analysis

struct AnalysisStatus: Codable {
    let sessionId: String
    let status: String
    let progressPct: Double

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case status
        case progressPct = "progress_pct"
    }
}

// MARK: - Clips

struct Clip: Codable, Identifiable {
    let id: String
    let sessionId: String
    let difficulty: String?
    let result: String?
    let isMe: Bool?
    let startTime: Double?
    let endTime: Double?
    let thumbnailUrl: String?

    enum CodingKeys: String, CodingKey {
        case id
        case sessionId = "session_id"
        case difficulty
        case result
        case isMe = "is_me"
        case startTime = "start_time"
        case endTime = "end_time"
        case thumbnailUrl = "thumbnail_url"
    }
}

struct ClipFilter {
    var difficulty: String?
    var result: String?
    var isMe: Bool?
}

struct ClipsResponse: Codable {
    let clips: [Clip]
}

// MARK: - Push

struct RegisterPushRequest: Codable {
    let deviceToken: String

    enum CodingKeys: String, CodingKey {
        case deviceToken = "device_token"
    }
}
