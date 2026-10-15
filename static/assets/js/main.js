import { auth, navigate, render, route } from "./core.js";
import * as S from "./student.js";
import * as A from "./admin.js";
import * as A2 from "./admin2.js";
import * as L from "./learn.js";

route("/", () => navigate(auth.user ? (auth.user.role === "admin" ? "/admin" : "/app") : "/login", { replace: true }));
route("/login", S.loginPage);
route("/register", S.registerPage);
route("/verify/:code", S.verifyPage);

route("/app", S.dashboardPage, { role: "student" });
route("/app/placement", S.placementPage, { role: "student" });
route("/app/learn", S.learnPage, { role: "student" });
route("/app/interview", S.interviewPage, { role: "student" });
route("/app/ask", L.askPage, { role: "student" });
route("/app/library", L.libraryPage, { role: "student" });
route("/app/session/:id", S.sessionPage, { role: "student" });
route("/app/progress", S.progressPage, { role: "student" });
route("/app/certificate", S.certificatePage, { role: "student" });
route("/app/profile", S.profilePage, { role: "student" });

route("/admin", A.overviewPage, { role: "admin" });
route("/admin/students", A.studentsPage, { role: "admin" });
route("/admin/students/:id", A.studentDetailPage, { role: "admin" });
route("/admin/sessions/:id", A.sessionDetailPage, { role: "admin" });
route("/admin/questions", A.questionsPage, { role: "admin" });
route("/admin/agents", A.agentsPage, { role: "admin" });
route("/admin/agents/:id", A.runDetailPage, { role: "admin" });
route("/admin/certificates", A.certificatesPage, { role: "admin" });
route("/admin/orgs", A.orgsPage, { role: "admin" });
route("/admin/settings", A.settingsPage, { role: "admin" });
route("/admin/audit", A.auditPage, { role: "admin" });
route("/admin/kb", A2.kbPage, { role: "admin" });
route("/admin/model", A2.modelPage, { role: "admin" });
route("/admin/factory", A2.factoryPage, { role: "admin" });

history.replaceState({ depth: 0 }, "", location.pathname + location.search);
render();
