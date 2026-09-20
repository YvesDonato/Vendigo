export function proxy(request: Request) {
  if (process.env.LID_API_ONLY === "1" && !["/api/v1/lid", "/lid-openapi.json"].includes(new URL(request.url).pathname)) {
    return Response.json({ error: "Not found." }, { status: 404, headers: { "Cache-Control": "no-store" } });
  }
}
