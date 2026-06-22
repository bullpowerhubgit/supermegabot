import { createClient } from '@supabase/supabase-js';
const supabaseUrl = process.env.REACT_APP_SUPABASE_URL || 'https://qyrjeckzacjaazkpvnjk.supabase.co';
const supabaseAnonKey = process.env.REACT_APP_SUPABASE_ANON_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF5cmplY2t6YWNqYWF6a3B2bmprIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzAxMzM2NDcsImV4cCI6MjA4NTcwOTY0N30._sz_ZD43fLfmcrDEWfNmeVOXUFVswD8F_VJqJ0zEC5Y';
export const supabase = createClient(supabaseUrl, supabaseAnonKey);
export interface User { id: string; email: string; plan: string; plan_status: string; }
export async function getCurrentUser(): Promise<User | null> {
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return null;
  try {
    const { data } = await supabase.from('users').select('plan, plan_status').eq('id', user.id).single();
    return { id: user.id, email: user.email || '', plan: data?.plan || 'pro', plan_status: data?.plan_status || 'active' };
  } catch {
    return { id: user.id, email: user.email || '', plan: 'pro', plan_status: 'active' };
  }
}
export async function signIn(email: string, password: string) {
  return await supabase.auth.signInWithPassword({ email, password });
}
export async function signUp(email: string, password: string) {
  return await supabase.auth.signUp({ email, password });
}
export async function signOut() { await supabase.auth.signOut(); }
