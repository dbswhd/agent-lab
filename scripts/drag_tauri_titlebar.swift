import CoreGraphics
import Foundation

let ownerName = CommandLine.arguments.dropFirst().first ?? "agent-lab-app"
let options: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
guard
  let rows = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[String: Any]],
  let row = rows.first(where: {
    ($0[kCGWindowOwnerName as String] as? String) == ownerName
      && ($0[kCGWindowLayer as String] as? Int) == 0
  }),
  let boundsDict = row[kCGWindowBounds as String] as? NSDictionary,
  let bounds = CGRect(dictionaryRepresentation: boundsDict)
else {
  fputs("Could not find an on-screen \(ownerName) window.\n", stderr)
  exit(1)
}

let source = CGEventSource(stateID: .hidSystemState)
let start = CGPoint(x: bounds.midX, y: bounds.minY + 20)
let finish = CGPoint(x: start.x + 48, y: start.y + 36)

guard CGPreflightPostEventAccess() else {
  fputs("Synthetic titlebar drag requires macOS Input Monitoring permission.\n", stderr)
  exit(2)
}

func post(_ type: CGEventType, at point: CGPoint) {
  CGEvent(
    mouseEventSource: source,
    mouseType: type,
    mouseCursorPosition: point,
    mouseButton: .left
  )?.post(tap: .cghidEventTap)
}

post(.leftMouseDown, at: start)
for step in 1...8 {
  let progress = CGFloat(step) / 8
  post(
    .leftMouseDragged,
    at: CGPoint(
      x: start.x + (finish.x - start.x) * progress,
      y: start.y + (finish.y - start.y) * progress
    )
  )
  usleep(20_000)
}
post(.leftMouseUp, at: finish)
usleep(250_000)

print("Dragged \(ownerName) titlebar from \(start) to \(finish)")
