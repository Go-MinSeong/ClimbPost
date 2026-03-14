import Foundation

extension Clip: Hashable {
    static func == (lhs: Clip, rhs: Clip) -> Bool {
        lhs.id == rhs.id
    }

    func hash(into hasher: inout Hasher) {
        hasher.combine(id)
    }
}
