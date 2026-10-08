import { redirect } from "next/navigation";

// The login form is the home page; /login only keeps old links and bookmarks working
export default function LoginPage() {
    redirect("/");
}
