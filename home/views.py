from django.shortcuts import redirect, render


def index(request):
    if not request.user.is_authenticated:
        return render(request, "home/home.html", {})
    return redirect("bookmark_list", slug=request.user.slug)
