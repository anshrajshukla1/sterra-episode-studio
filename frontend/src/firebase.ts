import { initializeApp } from 'firebase/app'
import { getAuth, signInWithEmailAndPassword, signOut, onAuthStateChanged, GoogleAuthProvider, signInWithPopup } from 'firebase/auth'
import type { User } from 'firebase/auth'

const isDummy = import.meta.env.VITE_FIREBASE_API_KEY === 'dummy' || !import.meta.env.VITE_FIREBASE_API_KEY

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
}

export const app = isDummy ? {} as any : initializeApp(firebaseConfig)
export const auth = isDummy ? {} as any : getAuth(app)

export async function getIdToken(): Promise<string | null> {
  if (isDummy) return 'dummy-token'
  const user = auth.currentUser
  if (!user) return null
  return user.getIdToken()
}

export const googleProvider = isDummy ? {} as any : new GoogleAuthProvider()

// Mock onAuthStateChanged for dummy mode
const safeOnAuthStateChanged = isDummy 
  ? (auth: any, cb: (user: any) => void) => {
      // Simulate an immediate logged-in dummy user
      setTimeout(() => cb({ uid: 'dummy', email: 'dev@local' }), 100)
      return () => {}
    }
  : onAuthStateChanged

const safeSignInWithEmailAndPassword = isDummy
  ? async () => ({ user: { uid: 'dummy' } } as any)
  : signInWithEmailAndPassword

const safeSignInWithPopup = isDummy
  ? async () => ({ user: { uid: 'dummy' } } as any)
  : signInWithPopup

const safeSignOut = isDummy
  ? async () => {}
  : signOut

export { 
  safeSignInWithEmailAndPassword as signInWithEmailAndPassword, 
  safeSignInWithPopup as signInWithPopup, 
  safeSignOut as signOut, 
  safeOnAuthStateChanged as onAuthStateChanged 
}
export type { User }
