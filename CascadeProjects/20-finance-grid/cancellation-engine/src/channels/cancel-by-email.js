import nodemailer from 'nodemailer';
import { buildCancellationEmail } from '../templates/cancellation-email-template.js';

export async function cancelByEmail(provider, contract) {
  const transporter = nodemailer.createTransport({
    host: process.env.SMTP_HOST,
    port: Number(process.env.SMTP_PORT || 587),
    secure: false,
    auth: {
      user: process.env.SMTP_USER,
      pass: process.env.SMTP_PASS
    }
  });

  const email = buildCancellationEmail(contract);

  await transporter.sendMail({
    from: process.env.SMTP_FROM,
    to: provider.cancelEmail,
    subject: email.subject,
    text: email.text
  });

  return {
    success: true,
    channel: 'email'
  };
}
