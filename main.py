from pathlib import Path
from typing import List, Optional
from rich.console import Console
import typer

app = typer.Typer(
    name="instarag",
    help="instarag -- Personal multi-source creator knowledge library and grounded RAG.",
    add_completion=False,
)

user_app = typer.Typer(help="Manage local user accounts.")
app.add_typer(user_app, name="user")

instagram_app = typer.Typer(help="Add Instagram creators to a library.")
app.add_typer(instagram_app, name="instagram")

tiktok_app = typer.Typer(help="Add TikTok videos or profiles to a library.")
app.add_typer(tiktok_app, name="tiktok")

group_app = typer.Typer(help="Manage scoped RAG agents / collections (Groups) and sharing.")
app.add_typer(group_app, name="group")

library_app = typer.Typer(help="Manage personal creator-content libraries.")
app.add_typer(library_app, name="library")

saved_app = typer.Typer(help="Import and process Instagram saved posts per user.")
app.add_typer(saved_app, name="saved")

console = Console()


def _get_active_user(user_opt: Optional[str]) -> str:
    from config.users import list_users, resolve_user
    user = resolve_user(user_opt)
    if not user:
        all_users = list_users()
        if len(all_users) == 1:
            return all_users[0].id
        console.print("[bold red]User not specified and no default found. Use '--user <username>' or set INSTARAG_USER env var.[/bold red]")
        raise typer.Exit(1)
    return user.id


@instagram_app.command("add")
def instagram_add_cmd(
    username: str = typer.Argument(..., help="Instagram username, post URL, or reel URL"),
    library: Optional[str] = typer.Option(None, "--library", "-l", help="Library slug"),
    max_posts: int = typer.Option(20, "--max-posts", help="Maximum posts to ingest"),
    newer_than: Optional[str] = typer.Option(None, "--newer-than"),
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Library owner username"),
):
    """Ingest an Instagram creator or post/reel URL into a library."""
    from src.pipeline import add_reel, resolve_library, scrape_profile

    owner_id = _get_active_user(user)
    library_id = resolve_library(owner_id, library)
    if username.startswith(("http://", "https://")):
        result = add_reel(
            [username],
            library_id=library_id,
            progress=console.print,
        )
        if result["failed"]:
            raise typer.BadParameter(result["failed"][0]["error"])
        console.print("[bold green]Instagram URL added.[/bold green]")
        return
    result = scrape_profile(
        username=username.lstrip("@"),
        library_id=library_id,
        max_posts=max_posts,
        newer_than=newer_than,
        progress=console.print,
    )
    console.print(
        f"[bold green]Instagram @{username.lstrip('@')} added: "
        f"{result['processed']} processed, {result['failed']} failed.[/bold green]"
    )


@tiktok_app.command("add")
def tiktok_add_cmd(
    url: str = typer.Argument(..., help="TikTok video or profile URL"),
    library: Optional[str] = typer.Option(None, "--library", "-l", help="Library slug"),
    caption_only: bool = typer.Option(False, "--caption-only"),
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Library owner username"),
):
    """Ingest a TikTok video or discover videos from a profile."""
    _add_social_url(url, library, caption_only, user, "TikTok")


def _add_social_url(
    url: str,
    library: Optional[str],
    caption_only: bool,
    user: Optional[str],
    platform_label: str,
) -> None:
    from src.pipeline import ingest_urls, resolve_library

    owner_id = _get_active_user(user)
    result = ingest_urls(
        resolve_library(owner_id, library),
        [url],
        owner_id=owner_id,
        caption_only=caption_only,
        progress=console.print,
    )
    if result["failed"]:
        raise typer.BadParameter(result["failed"][0]["error"])
    console.print(
        f"[bold green]{platform_label} source(s) added: "
        f"{len(result['added'])}.[/bold green]"
    )


@user_app.command("create")
def user_create(username: str = typer.Argument(..., help="Username for the new account")):
    from config.users import create_user, load_user
    if load_user(username):
        console.print(f"[bold yellow]User '{username}' already exists.[/bold yellow]")
        return
    user = create_user(username)
    console.print(f"[bold green]User '{user.username}' created successfully (ID: {user.id}).[/bold green]")


@user_app.command("list")
def user_list():
    from config.users import list_users
    users = list_users()
    if not users:
        console.print("[yellow]No users found. Create one with 'user create <username>'.[/yellow]")
        return
    console.print("[bold blue]Registered Users:[/bold blue]")
    for u in users:
        console.print(f"  - [bold]{u.username}[/bold] (ID: {u.id})")


@group_app.command("create")
def group_create_cmd(
    name: str = typer.Argument(..., help="Name of the RAG agent/group"),
    description: str = typer.Option("", "--desc", "-d", help="Description of the group agent"),
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Username owner"),
):
    from config.groups import create_group, load_group_by_name
    uid = _get_active_user(user)
    if load_group_by_name(uid, name):
        console.print(f"[bold yellow]Group '{name}' already exists for this account.[/bold yellow]")
        return
    g = create_group(uid, name, description)
    console.print(f"[bold green]Created RAG Agent group '{g.name}' (ID: {g.id}).[/bold green]")


@group_app.command("list")
def group_list_cmd(
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Username"),
):
    from config.groups import list_groups_for_user
    uid = _get_active_user(user)
    groups = list_groups_for_user(uid)
    if not groups:
        console.print("[yellow]No groups found. Create one with 'group create <name>'.[/yellow]")
        return
    console.print("[bold blue]Your RAG Agent Groups:[/bold blue]")
    for g in groups:
        owner_tag = "[green](owner)[/green]" if g.owner_id == uid else "[yellow](shared)[/yellow]"
        console.print(f"  - [bold]{g.name}[/bold] {owner_tag} | Posts: {g.post_count} | Desc: {g.description or '-'}")


@group_app.command("add-post")
def group_add_post_cmd(
    group_name: str = typer.Argument(..., help="Group name"),
    url_or_id: str = typer.Argument(..., help="Post URL or shortcode ID"),
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Account username"),
):
    from config.groups import add_post_to_group, load_group_by_name
    from src.pipeline import add_reel

    uid = _get_active_user(user)
    group = load_group_by_name(uid, group_name)
    if not group:
        console.print(f"[bold red]Group '{group_name}' not found.[/bold red]")
        raise typer.Exit(1)

    if url_or_id.startswith("http"):
        add_reel([url_or_id], group_id=group.id, progress=console.print)
    else:
        add_post_to_group(group.id, url_or_id)
        console.print(f"[bold green]Added post {url_or_id} to group '{group_name}'.[/bold green]")


@group_app.command("share")
def group_share_cmd(
    group_name: str = typer.Argument(..., help="Group name to share"),
    target_user: str = typer.Argument(..., help="Target username to grant access"),
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Owner username"),
):
    from config.groups import load_group_by_name, share_group
    from config.users import load_user

    uid = _get_active_user(user)
    group = load_group_by_name(uid, group_name)
    if not group or group.owner_id != uid:
        console.print(f"[bold red]You are not the owner of group '{group_name}'.[/bold red]")
        raise typer.Exit(1)

    t_user = load_user(target_user)
    if not t_user:
        console.print(f"[bold red]Target user '{target_user}' does not exist.[/bold red]")
        raise typer.Exit(1)

    if share_group(group.id, t_user.id):
        console.print(f"[bold green]Shared group '{group_name}' with '{target_user}'.[/bold green]")
    else:
        console.print(f"[yellow]Group was already shared with '{target_user}'.[/yellow]")


@saved_app.command("import")
def saved_import_cmd(
    path: Path = typer.Argument(..., help="Path to your Instagram zip export or saved_posts.json"),
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Account username"),
):
    from src.pipeline import import_user_saved_posts
    uid = _get_active_user(user)
    try:
        res = import_user_saved_posts(uid, path)
        console.print(f"[bold green]Imported {res['total']} saved posts ({res['new_saved']} new bookmarks)![/bold green]")
    except Exception as e:
        console.print(f"[bold red]Import failed:[/bold red] {e}")
        raise typer.Exit(1)


@library_app.command("create")
def library_create_cmd(
    name: str = typer.Argument(..., help="Library name"),
    description: str = typer.Option("", "--desc", "-d"),
    user: Optional[str] = typer.Option(None, "--user", "-u"),
):
    from src.pipeline import create_library
    result = create_library(_get_active_user(user), name, description)
    console.print(f"[bold green]Library '{result['name']}' (slug: {result['slug']})[/bold green]")


@library_app.command("list")
def library_list_cmd(user: Optional[str] = typer.Option(None, "--user", "-u")):
    from src.pipeline import list_libraries
    libraries = list_libraries(_get_active_user(user))
    if not libraries:
        console.print("[yellow]No libraries found. Create one with 'library create <name>'.[/yellow]")
        return
    for item in libraries:
        console.print(f"- [bold]{item['name']}[/bold] (slug: {item['slug']})")


@library_app.command("add-url")
def library_add_url_cmd(
    library_id: str = typer.Argument(..., help="Library ID"),
    urls: List[str] = typer.Argument(..., help="Public video URLs"),
    caption_only: bool = typer.Option(False, "--caption-only"),
    keep_media: bool = typer.Option(False, "--keep-media"),
):
    from src.pipeline import ingest_urls
    from src.pipeline import resolve_library
    owner_id = _get_active_user(None)
    result = ingest_urls(
        resolve_library(owner_id, library_id),
        urls,
        owner_id=owner_id,
        caption_only=caption_only,
        keep_media=keep_media,
        progress=console.print,
    )
    console.print(f"[bold green]Added {len(result['added'])} source(s); failed {len(result['failed'])}.[/bold green]")


@saved_app.command("process")
def saved_process_cmd(
    limit: Optional[int] = typer.Option(None, "--limit", help="Max pending posts to process"),
    caption_only: bool = typer.Option(False, "--caption-only", help="Skip media download"),
    workers: int = typer.Option(4, "--workers", help="Worker count"),
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Account username"),
):
    from src.pipeline import process_saved
    uid = _get_active_user(user)
    try:
        res = process_saved(uid, limit=limit, caption_only=caption_only, workers=workers, progress=console.print)
        console.print(f"\n[bold green]Finished processing saved posts![/bold green] Processed: {res['processed']}, Already Indexed: {res['already_indexed']}, Failed: {res['failed']}")
    except Exception as e:
        console.print(f"[bold red]Processing failed:[/bold red] {e}")
        raise typer.Exit(1)


@app.command("query")
def query_cmd(
    question: str = typer.Argument(..., help="Question to ask"),
    group: Optional[str] = typer.Option(None, "--group", "-g", help="Scope question to a specific RAG agent group"),
    library: Optional[str] = typer.Option(None, "--library", "-l", help="Scope question to a personal library ID"),
    creator: Optional[str] = typer.Option(None, "--creator", "-c", help="Scope question to a creator"),
    mode: str = typer.Option("grounded_plus", "--mode", help="'grounded_plus' or 'strict'"),
    artifact: Optional[str] = typer.Option(None, "--artifact", "-a", help="'workout_plan', 'recipe_book', or 'grocery_list'"),
    export: Optional[str] = typer.Option(None, "--export", "-o", help="Export to file (.md or .pdf)"),
    top_k: int = typer.Option(6, "--top-k", help="Top matches"),
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Account username"),
):
    from src.pipeline import query_knowledge
    from src.rag.artifacts import export_artifact
    uid = None
    if group or library:
        uid = _get_active_user(user)

    try:
        from src.pipeline import resolve_library
        resolved_library = resolve_library(uid, library) if library else None
        res = query_knowledge(
            question,
            creator=creator,
            group_name=group,
            library_id=resolved_library,
            user_id=uid,
            top_k=top_k,
            mode=mode,
            artifact_type=artifact,
            export_path=export,
        )
        console.print("\n[bold green]=== Answer ===[/bold green]\n")
        console.print(res["answer"])
        timings = res.get("timings_ms")
        if timings:
            console.print(
                "\n[dim]Timing: "
                + ", ".join(f"{name}={value:.0f}ms" for name, value in timings.items())
                + "[/dim]"
            )
        if res.get("sources"):
            console.print("\n[bold yellow]Sources:[/bold yellow]")
            for i, s in enumerate(res["sources"], 1):
                if s.get("cited", True):
                    summary_str = f" [dim]({s['summary']})[/dim]" if s.get("summary") else ""
                    console.print(f" - [Source {i}] @{s['creator']}: {s['url']}{summary_str}")

        if res.get("artifact"):
            art = res["artifact"]
            console.print(f"\n[bold green][OK] Document delegated & saved to:[/bold green] [cyan]{art['path']}[/cyan] [dim]({art['title']})[/dim]")
    except Exception as e:
        console.print(f"[bold red]Query failed:[/bold red] {e}")
        raise typer.Exit(1)





@app.command("chat")
def chat_cmd(
    group: Optional[str] = typer.Option(None, "--group", "-g", help="Scope chat to a specific RAG agent group"),
    library: Optional[str] = typer.Option(None, "--library", "-l", help="Scope chat to a personal library ID"),
    creator: Optional[str] = typer.Option(None, "--creator", "-c", help="Scope chat to a creator"),
    mode: str = typer.Option("grounded_plus", "--mode", help="'grounded_plus' or 'strict'"),
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Account username"),
):
    from src.pipeline import query_knowledge
    uid = None
    if group or library:
        uid = _get_active_user(user)

    history = []
    scope_desc = f"Group '{group}'" if group else (f"Library '{library}'" if library else (f"@{creator}" if creator else "Global Knowledge"))
    console.print(f"[bold blue]InstaRAG Chat ({scope_desc})[/bold blue] — type 'exit' to quit.")

    while True:
        try:
            q = console.input("\n[bold cyan]You:[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or q.lower() in ("exit", "quit", "salir"):
            break

        try:
            from src.pipeline import resolve_library
            resolved_library = resolve_library(uid, library) if library else None
            res = query_knowledge(q, creator=creator, group_name=group, library_id=resolved_library, user_id=uid, mode=mode, history=history)
            console.print(f"\n[bold green]Assistant:[/bold green]\n{res['answer']}")
            timings = res.get("timings_ms")
            if timings:
                console.print(
                    "[dim]"
                    + ", ".join(f"{name}={value:.0f}ms" for name, value in timings.items())
                    + "[/dim]"
                )
            if res.get("artifact"):
                art = res["artifact"]
                console.print(f"\n[bold green][OK] Document generated & saved to:[/bold green] [cyan]{art['path']}[/cyan]")
            history.append({"role": "user", "content": q})
            history.append({"role": "assistant", "content": res["answer"]})
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")



def main():
    from storage.db import init_db
    init_db()
    app()


if __name__ == "__main__":
    main()

