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
    let id: String
}

struct UploadResponse: Codable {
    let id: String
    let fileUrl: String?

    enum CodingKeys: String, CodingKey {
        case id
        case fileUrl = "file_url"
    }
}

struct StartAnalysisResponse: Codable {
    let id: String
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
    let rawVideoId: String
    let gymId: String?
    let difficulty: String?
    let tapeColor: String?
    let result: String?
    let isMe: Bool?
    let startTime: Double?
    let endTime: Double?
    let durationSec: Double?
    let thumbnailUrl: String?
    let clipUrl: String?
    let editedUrl: String?
    let createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case rawVideoId = "raw_video_id"
        case gymId = "gym_id"
        case difficulty
        case tapeColor = "tape_color"
        case result
        case isMe = "is_me"
        case startTime = "start_time"
        case endTime = "end_time"
        case durationSec = "duration_sec"
        case thumbnailUrl = "thumbnail_url"
        case clipUrl = "clip_url"
        case editedUrl = "edited_url"
        case createdAt = "created_at"
    }
}

struct ClipFilter {
    var difficulty: String?
    var result: String?
    var isMe: Bool?
}

// MARK: - Instagram Auth

struct InstagramConnectInfo: Codable {
    let fbAppId: String
    let redirectUri: String
    let scopes: String
    enum CodingKeys: String, CodingKey {
        case fbAppId = "fb_app_id"
        case redirectUri = "redirect_uri"
        case scopes
    }
}

struct InstagramCodeExchange: Codable {
    let code: String
}

struct InstagramAccountStatus: Codable {
    let igUsername: String?
    let igProfilePicture: String?
    let connected: Bool
    enum CodingKeys: String, CodingKey {
        case igUsername = "ig_username"
        case igProfilePicture = "ig_profile_picture"
        case connected
    }
}

// MARK: - Instagram Publish

struct InstagramPublishRequest: Codable {
    let clipIds: [String]
    let caption: String?
    enum CodingKeys: String, CodingKey {
        case clipIds = "clip_ids"
        case caption
    }
}

struct InstagramPublishResponse: Codable {
    let jobId: String
    let status: String
    enum CodingKeys: String, CodingKey {
        case jobId = "job_id"
        case status
    }
}

struct InstagramPublishStatus: Codable {
    let jobId: String
    let status: String
    let errorMessage: String?
    let igMediaId: String?
    enum CodingKeys: String, CodingKey {
        case jobId = "job_id"
        case status
        case errorMessage = "error_message"
        case igMediaId = "ig_media_id"
    }
}

// MARK: - Push

struct RegisterPushRequest: Codable {
    let deviceToken: String

    enum CodingKeys: String, CodingKey {
        case deviceToken = "device_token"
    }
}
