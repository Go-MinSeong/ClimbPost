import SwiftUI

struct UploadView: View {
    let videos: [DetectedVideo]

    @StateObject private var uploadState = UploadState()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 24) {
            if uploadState.isComplete {
                completedView
            } else if uploadState.isUploading {
                uploadingView
            } else if let error = uploadState.errorMessage {
                errorView(error)
            } else {
                // Initial state — auto-start upload
                ProgressView("Preparing upload...")
            }
        }
        .padding()
        .navigationTitle("Upload")
        .navigationBarBackButtonHidden(uploadState.isUploading)
        .task {
            await UploadService.shared.uploadVideos(videos, state: uploadState)
        }
    }

    // MARK: - Subviews

    private var uploadingView: some View {
        VStack(spacing: 20) {
            Spacer()

            Image(systemName: "arrow.up.circle")
                .font(.system(size: 48))
                .foregroundStyle(.blue)

            Text("Uploading Videos")
                .font(.title2.bold())

            // Overall progress
            VStack(spacing: 8) {
                ProgressView(value: uploadState.progress)
                    .progressViewStyle(.linear)

                Text("File \(uploadState.currentFileIndex) of \(uploadState.totalFiles)")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                Text("\(Int(uploadState.progress * 100))%")
                    .font(.title3.bold())
                    .monospacedDigit()
            }
            .padding(.horizontal)

            // Per-file progress list
            VStack(alignment: .leading, spacing: 8) {
                ForEach(videos) { video in
                    HStack {
                        let fileProg = uploadState.fileProgress[video.id] ?? 0
                        Image(systemName: fileProg >= 1.0 ? "checkmark.circle.fill" : "circle")
                            .foregroundStyle(fileProg >= 1.0 ? .green : .secondary)
                            .font(.caption)

                        Text(video.gym.name)
                            .font(.caption)
                            .lineLimit(1)

                        Spacer()

                        if fileProg >= 1.0 {
                            Text("Done")
                                .font(.caption2)
                                .foregroundStyle(.green)
                        } else if fileProg > 0 {
                            Text("\(Int(fileProg * 100))%")
                                .font(.caption2)
                                .monospacedDigit()
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .padding()
            .background(Color(.systemGroupedBackground))
            .cornerRadius(12)

            Text("You can leave the app — uploads will continue in the background.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            Spacer()
        }
    }

    private var completedView: some View {
        VStack(spacing: 20) {
            Spacer()

            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 64))
                .foregroundStyle(.green)

            Text("Upload Complete!")
                .font(.title2.bold())

            Text("\(videos.count) videos uploaded successfully.\nAnalysis has started — you'll get a notification when it's ready.")
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            Button("Done") {
                dismiss()
            }
            .buttonStyle(.borderedProminent)

            Spacer()
        }
    }

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 20) {
            Spacer()

            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 48))
                .foregroundStyle(.orange)

            Text("Upload Failed")
                .font(.title2.bold())

            Text(message)
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            HStack(spacing: 16) {
                Button("Go Back") {
                    dismiss()
                }
                .buttonStyle(.bordered)

                Button("Retry") {
                    uploadState.reset()
                    Task {
                        await UploadService.shared.uploadVideos(videos, state: uploadState)
                    }
                }
                .buttonStyle(.borderedProminent)
            }

            Spacer()
        }
    }
}
