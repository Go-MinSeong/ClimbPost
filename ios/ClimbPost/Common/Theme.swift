import SwiftUI

enum AppColor {
    static let accent = Color(red: 1.0, green: 0.42, blue: 0.21)     // #FF6B35 coral
    static let accentDark = Color(red: 0.9, green: 0.35, blue: 0.15)
    static let background = Color(red: 0.1, green: 0.1, blue: 0.18)  // #1A1A2E dark navy
    static let cardBackground = Color(red: 0.15, green: 0.15, blue: 0.22)
    static let success = Color(red: 0.2, green: 0.8, blue: 0.4)      // green
    static let fail = Color(red: 1.0, green: 0.3, blue: 0.3)         // red

    // Difficulty colors (matching tape colors)
    static func difficultyColor(_ difficulty: String?) -> Color {
        switch difficulty {
        case let d where d?.contains("V0") == true || d?.contains("V1") == true: return .yellow
        case let d where d?.contains("V2") == true || d?.contains("V3") == true: return .green
        case let d where d?.contains("V4") == true || d?.contains("V5") == true: return .blue
        case let d where d?.contains("V6") == true || d?.contains("V7") == true: return .red
        case let d where d?.contains("V8") == true: return .black
        default: return .gray
        }
    }
}

enum AppFont {
    static let heroTitle = Font.system(size: 36, weight: .black, design: .rounded)
    static let sectionTitle = Font.system(size: 20, weight: .bold, design: .rounded)
    static let cardTitle = Font.system(size: 16, weight: .semibold)
    static let badge = Font.system(size: 12, weight: .bold, design: .rounded)
    static let caption = Font.system(size: 12, weight: .medium)
}

// Reusable primary button style
struct PrimaryButtonStyle: ButtonStyle {
    var isEnabled: Bool = true
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 16, weight: .bold, design: .rounded))
            .frame(maxWidth: .infinity)
            .padding(.vertical, 16)
            .background(isEnabled ? AppColor.accent : Color.gray.opacity(0.3))
            .foregroundColor(.white)
            .clipShape(RoundedRectangle(cornerRadius: 14))
            .scaleEffect(configuration.isPressed ? 0.97 : 1.0)
            .animation(.easeInOut(duration: 0.15), value: configuration.isPressed)
    }
}
