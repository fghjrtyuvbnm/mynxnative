// The iPad launcher previews the same view and geometry the game uses.
import SwiftUI
import UIKit

enum TabletPadOptions {
    static let section = "Touch layout"
    static let size = choice("DM_TABLET_PAD_SIZE", "Control size", "100",
                             [["90", "Small"], ["100", "Medium"], ["110", "Large"]])
    static let lift = choice("DM_TABLET_PAD_LIFT", "Control height", "0",
                             [["-24", "Lower"], ["0", "Default"], ["24", "Higher"]])
    static let settings = [lift, size]

    private static func choice(_ env: String, _ label: String, _ value: String, _ options: [[String]]) -> Setting {
        Setting(env: env, kind: "choice", label: label, note: "", def: value,
                section: section, needs: nil, level: nil, base: nil, options: options,
                min: nil, max: nil, step: nil, on: nil, off: nil)
    }
}

struct TabletPadPreview: UIViewRepresentable {
    let playArea: CGSize
    let size: Double
    let lift: Double

    final class Container: UIView {
        private let pad = dm_tablet_pad_preview()
        var playArea: CGSize = .zero

        override init(frame: CGRect) {
            super.init(frame: frame)
            isUserInteractionEnabled = false
            addSubview(pad)
        }

        required init?(coder: NSCoder) { return nil }

        func update(playArea: CGSize, size: Double, lift: Double) {
            self.playArea = playArea
            dm_tablet_pad_preview_update(pad, size, lift)
            setNeedsLayout()
        }

        override func layoutSubviews() {
            super.layoutSubviews()
            guard playArea.width > 0, playArea.height > 0 else { return }
            let scale = min(bounds.width / playArea.width, bounds.height / playArea.height)
            pad.bounds = CGRect(origin: .zero, size: playArea)
            pad.center = CGPoint(x: bounds.midX, y: bounds.midY)
            pad.transform = CGAffineTransform(scaleX: scale, y: scale)
        }
    }

    func makeUIView(context: Context) -> Container { Container(frame: .zero) }

    func updateUIView(_ view: Container, context: Context) {
        view.update(playArea: playArea, size: size, lift: lift)
    }
}
