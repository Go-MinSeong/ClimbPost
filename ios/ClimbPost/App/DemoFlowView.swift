import SwiftUI

/// Demo view that auto-cycles through all screens and takes a "tour"
struct DemoFlowView: View {
    @State private var selectedTab = 0
    @State private var showResultDetail = false

    // Auto-advance tabs every 4 seconds for demo
    let timer = Timer.publish(every: 4, on: .main, in: .common).autoconnect()

    var body: some View {
        TabView(selection: $selectedTab) {
            // Tab 0: Home
            MainView()
                .tabItem { Label("홈", systemImage: "house.fill") }
                .tag(0)

            // Tab 1: Gallery (empty state - no photos in sim)
            NavigationStack {
                GalleryView()
            }
            .tabItem { Label("갤러리", systemImage: "photo.on.rectangle") }
            .tag(1)

            // Tab 2: Results
            NavigationStack {
                ResultView(sessionId: "e1f38a2a-fec8-4db2-9c02-28d3e82edc39")
            }
            .tabItem { Label("결과", systemImage: "film.stack") }
            .tag(2)

            // Tab 3: Carousel
            NavigationStack {
                CarouselView(sessionId: "e1f38a2a-fec8-4db2-9c02-28d3e82edc39", initialClip: nil)
            }
            .tabItem { Label("캐러셀", systemImage: "square.grid.2x2") }
            .tag(3)
        }
        .tint(AppColor.accent)
        .onReceive(timer) { _ in
            withAnimation {
                selectedTab = (selectedTab + 1) % 4
            }
        }
    }
}
