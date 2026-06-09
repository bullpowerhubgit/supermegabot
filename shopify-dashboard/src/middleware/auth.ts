import { createClient } from '@supabase/supabase-js';
const supabaseUrl = process.env.REACT_APP_SUPABASE_URL || '';
const supabaseAnonKey = process.env.REACT_APP_SUPABASE_ANON_KEY || '';
export const supabase = createClient(supabaseUrl, supabaseAnonKey);
export interface User { id: string; email: string; plan: string; plan_status: string; }
export async function getCurrentUser(): Promise<User | null> {
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return null;
  const { data } = await supabase.from('users').select('plan, plan_status').eq('id', user.id).single();
  return { id: user.id, email: user.email || '', plan: data?.plan || 'free', plan_status: data?.plan_status || 'active' };
}
export async function signIn(email: string, password: string) {
  return await supabase.auth.signInWithPassword({ email, password });
}
export async function signOut() { await supabase.auth.signOut(); }
