import UIKit
import UserNotifications

final class PushManager: NSObject, ObservableObject {
    static let shared = PushManager()

    @Published var pendingSessionId: String?

    override init() {
        super.init()
        UNUserNotificationCenter.current().delegate = self
    }

    /// Request notification permission and register for remote notifications.
    func requestAuthorization() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .badge, .sound]) { granted, error in
            guard granted, error == nil else { return }
            DispatchQueue.main.async {
                UIApplication.shared.registerForRemoteNotifications()
            }
        }
    }

    /// Called from AppDelegate when APNs returns a device token.
    func didRegisterForRemoteNotifications(deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
        Task {
            try? await APIClient.shared.registerPushToken(token)
        }
    }

    /// Called from AppDelegate on token registration failure.
    func didFailToRegisterForRemoteNotifications(error: Error) {
        print("Push registration failed: \(error.localizedDescription)")
    }

    /// Handle push payload — extract session_id for deep link to ResultView.
    func handleNotification(userInfo: [AnyHashable: Any]) {
        guard let sessionId = userInfo["session_id"] as? String else { return }
        DispatchQueue.main.async {
            self.pendingSessionId = sessionId
        }
    }
}

// MARK: - UNUserNotificationCenterDelegate

extension PushManager: UNUserNotificationCenterDelegate {
    /// Foreground notification — show banner even when app is active.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .badge, .sound])
    }

    /// User tapped notification — deep link to results.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        handleNotification(userInfo: response.notification.request.content.userInfo)
        completionHandler()
    }
}
