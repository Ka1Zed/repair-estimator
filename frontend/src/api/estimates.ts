import { apiClient } from './client';

export const calculateEstimate = async (payload: unknown) => {
  const data = await apiClient.calculateEstimate(payload);
  return data;
};
