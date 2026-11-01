import { authenticate } from "@/lib/session";

export const POST = (req: Request) => authenticate(req, "login");
