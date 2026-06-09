export function validateContract(contract, provider) {
  const errors = [];

  if (!contract.provider) errors.push('Missing provider');
  if (!contract.contractName) errors.push('Missing contract name');
  if (!contract.nextRenewalDate) errors.push('Missing next renewal date');
  if (provider.requiresCustomerNumber && !contract.customerNumber) {
    errors.push('Missing customer number');
  }

  return {
    valid: errors.length === 0,
    errors
  };
}
