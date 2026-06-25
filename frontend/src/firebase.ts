import { initializeApp } from 'firebase/app'
import { getAuth, signOut, onAuthStateChanged, GoogleAuthProvider, OAuthProvider, signInWithPopup } from 'firebase/auth'
import type { User } from 'firebase/auth'

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
}

export const isFirebaseConfigured = !!firebaseConfig.apiKey

if (!isFirebaseConfigured) {
  console.warn("⚠️ VITE_FIREBASE_API_KEY is not set. Firebase Authentication will fail. Please check your .env file.")
}

// Only initialize if configured, to prevent app crashing to a blank white screen
export const app = isFirebaseConfigured ? initializeApp(firebaseConfig) : null as any
export const auth = isFirebaseConfigured ? getAuth(app) : null as any

export async function getIdToken(): Promise<string | null> {
  const user = auth.currentUser
  if (!user) return null
  return user.getIdToken()
}

export const googleProvider = new GoogleAuthProvider()
export const appleProvider = new OAuthProvider('apple.com')

export { 
  signInWithPopup, 
  signOut, 
  onAuthStateChanged 
}
export type { User }
