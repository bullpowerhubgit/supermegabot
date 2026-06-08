export async function createManualLetter(provider, contract) {
  return {
    success: true,
    channel: 'manual-letter',
    message: `Create signed cancellation letter for ${provider.postalAddress}` 
  };
}
