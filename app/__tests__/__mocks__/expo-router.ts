export const useLocalSearchParams = jest.fn(() => ({ id: 'test-id' }));
export const useRouter = jest.fn(() => ({
  push: jest.fn(),
  back: jest.fn(),
  replace: jest.fn(),
}));
