import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || 'https://oumemgklvmafmstxshkh.supabase.co';
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || 'sb_publishable_CKth-JsWfgXBSxtkj9T14Q_N8RBSNBQ';

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
