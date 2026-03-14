import SwiftUI

struct ContentView: View {
    @EnvironmentObject var authState: AuthState

    var body: some View {
        Group {
            if authState.isLoading {
                ProgressView("Loading...")
            } else if authState.isLoggedIn {
                MainView()
            } else {
                LoginView()
            }
        }
        .task {
            await authState.checkExistingSession()
        }
    }
}

struct MainView: View {
    @EnvironmentObject var authState: AuthState

    var body: some View {
        NavigationStack {
            VStack(spacing: 24) {
                Image(systemName: "mountain.2.fill")
                    .font(.system(size: 60))
                    .foregroundStyle(.blue)

                Text("ClimbPost")
                    .font(.largeTitle.bold())

                if let user = authState.currentUser {
                    Text("Welcome, \(user.email ?? user.userId)")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                Text("Ready to analyze your climbing videos")
                    .font(.body)
                    .foregroundStyle(.secondary)
            }
            .navigationTitle("Home")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Sign Out") {
                        Task { await authState.signOut() }
                    }
                }
            }
        }
    }
}
