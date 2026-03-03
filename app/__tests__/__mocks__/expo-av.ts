export const Audio = {
  requestPermissionsAsync: jest.fn(() =>
    Promise.resolve({ granted: true, status: "granted" })
  ),
  setAudioModeAsync: jest.fn(() => Promise.resolve()),
  Recording: {
    createAsync: jest.fn(() =>
      Promise.resolve({
        recording: {
          stopAndUnloadAsync: jest.fn(() => Promise.resolve()),
          getURI: jest.fn(() => "file:///mock/recording.m4a"),
          getStatusAsync: jest.fn(() =>
            Promise.resolve({ durationMillis: 5000 })
          ),
        },
      })
    ),
  },
  RecordingOptionsPresets: {
    HIGH_QUALITY: {},
  },
};
