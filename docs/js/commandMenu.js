const content = document.getElementById("content");

function constructDescription(jsondata) {
    var output = "";
    if (jsondata["description"].length > 0) {
        output += jsondata["description"].join("</br>") + "</br></br>";
    }
    for (const [command, info] of Object.entries(jsondata["commands"])) {
        console.log(command);
        output += "<b>"+command+"</b>" + " - " + info.join("</br>") + "</br></br>";
    }
    return output;
}

function createCommandElements(jsondata) {
    for (const [key, value] of Object.entries(jsondata)) {
        const container = document.createElement("div");
        container.setAttribute("class", "command-container");
        const labelContainer = document.createElement("div");
        labelContainer.setAttribute("class", "command-label-container");
        const arrow = document.createElement("img");
        arrow.setAttribute("class", "arrow");
        arrow.setAttribute("src", "static/arrow-down.webp");
        const label = document.createElement("h1");
        label.setAttribute("class", "command-label");
        label.innerHTML = key;
        const descriptionContainer = document.createElement("div");
        descriptionContainer.setAttribute("class", "command-description-container");
        const description = document.createElement("p");
        description.setAttribute("class", "text command-description");
        description.innerHTML = constructDescription(value);

        content.appendChild(container);
        container.appendChild(labelContainer);
        container.appendChild(descriptionContainer);
        labelContainer.appendChild(arrow);
        labelContainer.appendChild(label);
        descriptionContainer.appendChild(description);

        labelContainer.style.cursor = "pointer";
        labelContainer.onclick = function() {
            if (arrow.src.endsWith("static/arrow-up.webp")) {
                arrow.src = "static/arrow-down.webp";
                descriptionContainer.style.display = "none";
            } else {
                arrow.src = "static/arrow-up.webp";
                descriptionContainer.style.display = "block";
            }
        };
    }
}

fetch("commands/commands.json").then(response => {
    return response.json();
}).then(jsondata => createCommandElements(jsondata));
