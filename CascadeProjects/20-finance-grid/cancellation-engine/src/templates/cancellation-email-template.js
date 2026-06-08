export function buildCancellationEmail(contract) {
  return {
    subject: `Kündigung: ${contract.contractName}`,
    text: `Sehr geehrte Damen und Herren,\n\nhiermit kündige ich den Vertrag ${contract.contractName}${contract.customerNumber ? `, Kundennummer ${contract.customerNumber}` : ''} fristgerecht zum nächstmöglichen Zeitpunkt.\n\nBitte bestätigen Sie mir die Kündigung schriftlich unter ${contract.confirmationEmail}.\n\nMit freundlichen Grüßen\n${contract.fullName}` 
  };
}
